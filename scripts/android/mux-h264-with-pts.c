#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <libavformat/avformat.h>
#include <libavutil/avutil.h>

typedef struct {
    int64_t *items;
    size_t count;
    size_t capacity;
} PtsList;

static void print_av_error(const char *operation, int error) {
    char message[AV_ERROR_MAX_STRING_SIZE] = {0};
    av_strerror(error, message, sizeof(message));
    fprintf(stderr, "%s: %s\n", operation, message);
}

static int append_pts(PtsList *list, int64_t value) {
    if (list->count == list->capacity) {
        size_t capacity = list->capacity == 0 ? 1024 : list->capacity * 2;
        int64_t *items = realloc(list->items, capacity * sizeof(*items));
        if (items == NULL) {
            return AVERROR(ENOMEM);
        }
        list->items = items;
        list->capacity = capacity;
    }
    list->items[list->count++] = value;
    return 0;
}

static int read_pts(const char *path, PtsList *list) {
    FILE *file = fopen(path, "r");
    if (file == NULL) {
        fprintf(stderr, "open %s: %s\n", path, strerror(errno));
        return AVERROR(errno);
    }

    char marker[32];
    long long packet_number;
    long long presentation_time_us;
    int flags;
    int packet_size;
    int result = 0;

    while (fscanf(file, "%31s %lld %lld %d %d", marker, &packet_number,
                  &presentation_time_us, &flags, &packet_size) == 5) {
        if (strcmp(marker, "__PTS__") != 0) {
            fprintf(stderr, "unexpected PTS marker: %s\n", marker);
            result = AVERROR_INVALIDDATA;
            break;
        }
        (void) packet_number;
        (void) packet_size;

        // MediaCodec writes SPS/PPS as BUFFER_FLAG_CODEC_CONFIG. FFmpeg folds
        // that packet into the first frame, so it has no separate frame PTS.
        if ((flags & 2) != 0) {
            continue;
        }
        if (list->count > 0
                && presentation_time_us < list->items[list->count - 1]) {
            fprintf(stderr, "non-monotonic PTS at frame %zu\n", list->count);
            result = AVERROR_INVALIDDATA;
            break;
        }
        result = append_pts(list, (int64_t) presentation_time_us);
        if (result < 0) {
            break;
        }
    }
    if (ferror(file)) {
        result = AVERROR(errno);
    } else if (result == 0 && list->count == 0) {
        fprintf(stderr, "no frame timestamps found in %s\n", path);
        result = AVERROR_INVALIDDATA;
    }
    fclose(file);
    return result;
}

static int64_t duration_us(const PtsList *list, size_t index) {
    int64_t duration = 40000;
    if (index + 1 < list->count) {
        duration = list->items[index + 1] - list->items[index];
    } else if (index > 0) {
        duration = list->items[index] - list->items[index - 1];
    }
    return duration > 0 ? duration : 1;
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "usage: %s INPUT.h264 INPUT.pts OUTPUT.mp4\n", argv[0]);
        return 2;
    }

    PtsList timestamps = {0};
    AVFormatContext *input = NULL;
    AVFormatContext *output = NULL;
    AVPacket *packet = NULL;
    AVDictionary *options = NULL;
    int input_video_index = -1;
    int result = read_pts(argv[2], &timestamps);
    if (result < 0) {
        goto cleanup;
    }

    result = avformat_open_input(
            &input, argv[1], av_find_input_format("h264"), NULL);
    if (result < 0) {
        print_av_error("open H.264 input", result);
        goto cleanup;
    }
    result = avformat_find_stream_info(input, NULL);
    if (result < 0) {
        print_av_error("read H.264 stream information", result);
        goto cleanup;
    }
    for (unsigned int i = 0; i < input->nb_streams; ++i) {
        if (input->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
            input_video_index = (int) i;
            break;
        }
    }
    if (input_video_index < 0) {
        result = AVERROR_STREAM_NOT_FOUND;
        goto cleanup;
    }

    result = avformat_alloc_output_context2(&output, NULL, "mp4", argv[3]);
    if (result < 0 || output == NULL) {
        print_av_error("create MP4 output", result);
        goto cleanup;
    }
    AVStream *output_stream = avformat_new_stream(output, NULL);
    if (output_stream == NULL) {
        result = AVERROR(ENOMEM);
        goto cleanup;
    }
    result = avcodec_parameters_copy(
            output_stream->codecpar, input->streams[input_video_index]->codecpar);
    if (result < 0) {
        print_av_error("copy video parameters", result);
        goto cleanup;
    }
    output_stream->codecpar->codec_tag = 0;
    output_stream->time_base = (AVRational) {1, 1000000};

    if ((output->oformat->flags & AVFMT_NOFILE) == 0) {
        result = avio_open(&output->pb, argv[3], AVIO_FLAG_WRITE);
        if (result < 0) {
            print_av_error("open MP4 output", result);
            goto cleanup;
        }
    }
    av_dict_set(&options, "movflags", "+faststart", 0);
    av_dict_set(&options, "video_track_timescale", "1000000", 0);
    result = avformat_write_header(output, &options);
    if (result < 0) {
        print_av_error("write MP4 header", result);
        goto cleanup;
    }

    packet = av_packet_alloc();
    if (packet == NULL) {
        result = AVERROR(ENOMEM);
        goto cleanup;
    }

    size_t frame_index = 0;
    int64_t origin_us = timestamps.items[0];
    while ((result = av_read_frame(input, packet)) >= 0) {
        if (packet->stream_index != input_video_index) {
            av_packet_unref(packet);
            continue;
        }
        if (frame_index >= timestamps.count) {
            fprintf(stderr, "H.264 has more frames than its PTS sidecar\n");
            result = AVERROR_INVALIDDATA;
            goto cleanup;
        }

        AVRational microseconds = {1, 1000000};
        packet->pts = timestamps.items[frame_index] - origin_us;
        packet->dts = packet->pts;
        packet->duration = duration_us(&timestamps, frame_index);
        packet->time_base = microseconds;
        packet->stream_index = output_stream->index;
        packet->pos = -1;
        av_packet_rescale_ts(packet, microseconds, output_stream->time_base);

        result = av_interleaved_write_frame(output, packet);
        if (result < 0) {
            print_av_error("write video packet", result);
            goto cleanup;
        }
        frame_index += 1;
    }
    if (result != AVERROR_EOF) {
        print_av_error("read H.264 packet", result);
        goto cleanup;
    }
    if (frame_index != timestamps.count) {
        fprintf(stderr, "frame count mismatch: H.264=%zu PTS=%zu\n",
                frame_index, timestamps.count);
        result = AVERROR_INVALIDDATA;
        goto cleanup;
    }
    result = av_write_trailer(output);
    if (result < 0) {
        print_av_error("write MP4 trailer", result);
        goto cleanup;
    }

    printf("muxed %zu frames with original PTS into %s\n",
            frame_index, argv[3]);
    result = 0;

cleanup:
    av_dict_free(&options);
    av_packet_free(&packet);
    avformat_close_input(&input);
    if (output != NULL) {
        if (output->pb != NULL && (output->oformat->flags & AVFMT_NOFILE) == 0) {
            avio_closep(&output->pb);
        }
        avformat_free_context(output);
    }
    free(timestamps.items);
    return result < 0 ? 1 : 0;
}
