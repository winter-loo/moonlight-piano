import android.hardware.input.InputManager;
import android.os.SystemClock;
import android.view.InputDevice;
import android.view.InputEvent;
import android.view.MotionEvent;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.reflect.Method;

/**
 * Persistent stdin-to-MotionEvent bridge run by app_process as Android's shell UID.
 *
 * Input lines are: KIND X Y SEQUENCE, where KIND is DOWN or UP.  Keeping one
 * VM and one InputManager connection alive avoids the process-start cost of
 * invoking Android's `input` utility for every musical boundary.
 */
public final class CodexInputBridge {
    private static final int INJECT_WAIT_FOR_FINISH = 2;
    private static final int FOUR_FINGER_HOLD_MS = 2200;

    private CodexInputBridge() {}

    public static void main(String[] args) throws Exception {
        Class<?> managerClass = Class.forName("android.hardware.input.InputManager");
        Method getInstance = managerClass.getDeclaredMethod("getInstance");
        getInstance.setAccessible(true);
        Object inputManager = getInstance.invoke(null);
        Method inject = managerClass.getDeclaredMethod(
                "injectInputEvent", InputEvent.class, int.class);
        inject.setAccessible(true);

        long activeDownTime = 0L;
        BufferedReader input = new BufferedReader(new InputStreamReader(System.in));
        String line;
        while ((line = input.readLine()) != null) {
            line = line.trim();
            if (line.equals("exit")) {
                break;
            }
            String[] fields = line.split("\\s+");
            if (fields.length == 2 && fields[0].equals("FOUR")) {
                boolean accepted = injectFourFingerHold(inputManager, inject);
                System.out.println(
                        "__ACK__" + fields[1] + " " + (accepted ? "1" : "0"));
                System.out.flush();
                continue;
            }
            if (fields.length != 4) {
                System.err.println("invalid command: " + line);
                continue;
            }

            String kind = fields[0];
            float x = Float.parseFloat(fields[1]);
            float y = Float.parseFloat(fields[2]);
            String sequence = fields[3];
            long eventTime = SystemClock.uptimeMillis();
            int action;
            if (kind.equals("DOWN")) {
                activeDownTime = eventTime;
                action = MotionEvent.ACTION_DOWN;
            } else if (kind.equals("UP")) {
                if (activeDownTime == 0L) {
                    activeDownTime = eventTime;
                }
                action = MotionEvent.ACTION_UP;
            } else {
                System.err.println("invalid action: " + kind);
                continue;
            }

            MotionEvent event = MotionEvent.obtain(
                    activeDownTime, eventTime, action, x, y, 0);
            event.setSource(InputDevice.SOURCE_TOUCHSCREEN);
            boolean accepted = (Boolean) inject.invoke(
                    inputManager, event, INJECT_WAIT_FOR_FINISH);
            event.recycle();
            if (action == MotionEvent.ACTION_UP) {
                activeDownTime = 0L;
            }
            System.out.println("__ACK__" + sequence + " " + (accepted ? "1" : "0"));
            System.out.flush();
        }
    }

    private static boolean injectFourFingerHold(Object inputManager, Method inject)
            throws Exception {
        float[] xs = {300f, 600f, 900f, 1200f};
        float y = 360f;
        MotionEvent.PointerProperties[] properties =
                new MotionEvent.PointerProperties[xs.length];
        MotionEvent.PointerCoords[] coordinates =
                new MotionEvent.PointerCoords[xs.length];
        for (int index = 0; index < xs.length; index++) {
            MotionEvent.PointerProperties pointer =
                    new MotionEvent.PointerProperties();
            pointer.id = index;
            pointer.toolType = MotionEvent.TOOL_TYPE_FINGER;
            properties[index] = pointer;

            MotionEvent.PointerCoords coords = new MotionEvent.PointerCoords();
            coords.x = xs[index];
            coords.y = y;
            coords.pressure = 1f;
            coords.size = 1f;
            coordinates[index] = coords;
        }

        long downTime = SystemClock.uptimeMillis();
        boolean accepted = injectPointers(
                inputManager,
                inject,
                downTime,
                MotionEvent.ACTION_DOWN,
                1,
                properties,
                coordinates);
        for (int count = 2; count <= xs.length; count++) {
            int action = MotionEvent.ACTION_POINTER_DOWN
                    | ((count - 1) << MotionEvent.ACTION_POINTER_INDEX_SHIFT);
            accepted &= injectPointers(
                    inputManager,
                    inject,
                    downTime,
                    action,
                    count,
                    properties,
                    coordinates);
        }

        Thread.sleep(FOUR_FINGER_HOLD_MS);
        for (int count = xs.length; count >= 2; count--) {
            int action = MotionEvent.ACTION_POINTER_UP
                    | ((count - 1) << MotionEvent.ACTION_POINTER_INDEX_SHIFT);
            accepted &= injectPointers(
                    inputManager,
                    inject,
                    downTime,
                    action,
                    count,
                    properties,
                    coordinates);
        }
        accepted &= injectPointers(
                inputManager,
                inject,
                downTime,
                MotionEvent.ACTION_UP,
                1,
                properties,
                coordinates);
        return accepted;
    }

    private static boolean injectPointers(
            Object inputManager,
            Method inject,
            long downTime,
            int action,
            int pointerCount,
            MotionEvent.PointerProperties[] properties,
            MotionEvent.PointerCoords[] coordinates)
            throws Exception {
        MotionEvent event = MotionEvent.obtain(
                downTime,
                SystemClock.uptimeMillis(),
                action,
                pointerCount,
                properties,
                coordinates,
                0,
                0,
                1f,
                1f,
                0,
                0,
                InputDevice.SOURCE_TOUCHSCREEN,
                0);
        boolean accepted = (Boolean) inject.invoke(
                inputManager, event, INJECT_WAIT_FOR_FINISH);
        event.recycle();
        return accepted;
    }
}
