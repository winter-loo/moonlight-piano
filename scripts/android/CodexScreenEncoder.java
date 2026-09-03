import android.graphics.Rect;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.os.IBinder;
import android.view.Surface;

import java.io.FileOutputStream;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;

/**
 * Minimal shell-UID display mirror that emits an Annex-B AVC stream on stdout.
 *
 * Run with app_process so the host can archive the encoded stream directly:
 *   CLASSPATH=/data/local/tmp/codex-screen-encoder.jar app_process /system/bin \
 *       CodexScreenEncoder WIDTH HEIGHT BITRATE FPS SECONDS ROTATION PTS_PATH
 *
 * Diagnostic frame PTS records go to stderr, keeping stdout a clean H.264 byte
 * stream. ROTATION uses Surface.ROTATION_* integer values (0 through 3).
 */
public final class CodexScreenEncoder {
    private static final long DEQUEUE_TIMEOUT_US = 100_000L;

    private CodexScreenEncoder() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 7) {
            System.err.println(
                    "usage: CodexScreenEncoder width height bitrate fps seconds rotation"
                            + " pts-path");
            System.exit(2);
        }

        int width = Integer.parseInt(args[0]);
        int height = Integer.parseInt(args[1]);
        int bitrate = Integer.parseInt(args[2]);
        int fps = Integer.parseInt(args[3]);
        double seconds = Double.parseDouble(args[4]);
        int rotation = Integer.parseInt(args[5]);
        String ptsPath = args[6];

        MediaFormat format = MediaFormat.createVideoFormat("video/avc", width, height);
        format.setInteger(
                MediaFormat.KEY_COLOR_FORMAT,
                MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
        format.setInteger(MediaFormat.KEY_BIT_RATE, bitrate);
        format.setInteger(MediaFormat.KEY_FRAME_RATE, fps);
        format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);
        format.setInteger(MediaFormat.KEY_BITRATE_MODE,
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR);

        MediaCodec codec = MediaCodec.createEncoderByType("video/avc");
        Surface inputSurface = null;
        IBinder displayToken = null;
        try {
            codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            inputSurface = codec.createInputSurface();
            codec.start();

            displayToken = attachDisplay(inputSurface, width, height, rotation);
            drain(codec, seconds, ptsPath);
        } finally {
            if (displayToken != null) {
                destroyDisplay(displayToken);
            }
            try {
                codec.stop();
            } catch (IllegalStateException ignored) {
                // The codec may not have reached STARTED if device setup failed.
            }
            codec.release();
            if (inputSurface != null) {
                inputSurface.release();
            }
        }
    }

    private static IBinder attachDisplay(
            Surface surface, int width, int height, int rotation) throws Exception {
        Class<?> surfaceControl = Class.forName("android.view.SurfaceControl");
        Method createDisplay = surfaceControl.getDeclaredMethod(
                "createDisplay", String.class, boolean.class);
        Method openTransaction = surfaceControl.getDeclaredMethod("openTransaction");
        Method closeTransaction = surfaceControl.getDeclaredMethod("closeTransaction");
        Method setDisplaySurface = surfaceControl.getDeclaredMethod(
                "setDisplaySurface", IBinder.class, Surface.class);
        Method setDisplayProjection = surfaceControl.getDeclaredMethod(
                "setDisplayProjection", IBinder.class, int.class, Rect.class, Rect.class);
        Method setDisplayLayerStack = surfaceControl.getDeclaredMethod(
                "setDisplayLayerStack", IBinder.class, int.class);
        createDisplay.setAccessible(true);
        openTransaction.setAccessible(true);
        closeTransaction.setAccessible(true);
        setDisplaySurface.setAccessible(true);
        setDisplayProjection.setAccessible(true);
        setDisplayLayerStack.setAccessible(true);

        IBinder token = (IBinder) createDisplay.invoke(null, "CodexScreenEncoder", false);
        Rect content = new Rect(0, 0, width, height);
        openTransaction.invoke(null);
        try {
            setDisplaySurface.invoke(null, token, surface);
            setDisplayProjection.invoke(null, token, rotation, content, content);
            setDisplayLayerStack.invoke(null, token, 0);
        } finally {
            closeTransaction.invoke(null);
        }
        return token;
    }

    private static void destroyDisplay(IBinder token) {
        try {
            Class<?> surfaceControl = Class.forName("android.view.SurfaceControl");
            Method destroyDisplay = surfaceControl.getDeclaredMethod(
                    "destroyDisplay", IBinder.class);
            destroyDisplay.setAccessible(true);
            destroyDisplay.invoke(null, token);
        } catch (Exception error) {
            System.err.println("destroy-display-error " + error);
        }
    }

    private static void drain(MediaCodec codec, double seconds, String ptsPath)
            throws Exception {
        OutputStream output = new FileOutputStream("/proc/self/fd/1");
        PrintWriter timestamps = new PrintWriter(new FileOutputStream(ptsPath));
        MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        long startedNs = System.nanoTime();
        long durationNs = (long) (seconds * 1_000_000_000L);
        int packet = 0;

        while (System.nanoTime() - startedNs < durationNs) {
            int index = codec.dequeueOutputBuffer(info, DEQUEUE_TIMEOUT_US);
            if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED
                    || index == MediaCodec.INFO_TRY_AGAIN_LATER) {
                continue;
            }
            if (index < 0) {
                continue;
            }

            ByteBuffer buffer = codec.getOutputBuffer(index);
            if (buffer != null && info.size > 0) {
                buffer.position(info.offset);
                buffer.limit(info.offset + info.size);
                byte[] bytes = new byte[info.size];
                buffer.get(bytes);
                output.write(bytes);
                packet += 1;
                timestamps.println(
                        "__PTS__ " + packet + " " + info.presentationTimeUs
                                + " " + info.flags + " " + info.size);
                timestamps.flush();
            }
            codec.releaseOutputBuffer(index, false);
        }
        output.flush();
        timestamps.close();
    }
}
