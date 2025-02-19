# SPDX-FileCopyrightText: Copyright (c) 2022 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

import argparse
from pathlib import Path

import riva.client
from riva.client.argparse_utils import add_asr_config_argparse_parameters, add_connection_argparse_parameters

import riva.client.audio_io


def parse_args() -> argparse.Namespace:
    default_device_info = riva.client.audio_io.get_default_input_device_info()
    default_device_index = None if default_device_info is None else default_device_info['index']
    parser = argparse.ArgumentParser(
        description="Streaming transcription from microphone via Riva AI Services",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input-device", type=int, default=default_device_index, help="An input audio device to use.")
    parser.add_argument("--list-devices", action="store_true", help="List input audio device indices.")
    parser = add_asr_config_argparse_parameters(parser, profanity_filter=True)
    parser = add_connection_argparse_parameters(parser)
    parser.add_argument(
        "--sample-rate-hz",
        type=int,
        help="A number of frames per second in audio streamed from a microphone.",
        default=16000,
    )
    parser.add_argument(
        "--file-streaming-chunk",
        type=int,
        default=1600,
        help="A maximum number of frames in a audio chunk sent to server.",
    )
    parser.add_argument(
        "--chatlog-role",
        type=str,
        default="User",
        help="Role str to prefix each line of transcript.",
    )
    parser.add_argument(
        "--chatlog-file",
        type=str,
        help="Path of output file for chat log.",
    )
    parser.add_argument(
        "--system-prompt-file",
        type=argparse.FileType('r'),
        help="File containing chat system prompt",
    )
    args = parser.parse_args()
    return args


def main() -> None:
    args = parse_args()
    if args.list_devices:
        riva.client.audio_io.list_input_devices()
        return

    chatlog_file_path = Path(args.chatlog_file)
    if not chatlog_file_path.is_file():
        print("chatlog file does not exist, creating it with system prompt.")
        chatlog_file = open(chatlog_file_path, 'w')
        #chatlog_file.write("System: " + args.system_prompt_file.read() + '\n')
    else:
        print("chatlog file exists, appending to it.")
        chatlog_file = open(chatlog_file_path, 'a')

    chatlog_file.write(args.chatlog_role + ": \n")
    auth = riva.client.Auth(args.ssl_cert, args.use_ssl, args.server)
    asr_service = riva.client.ASRService(auth)
    config = riva.client.StreamingRecognitionConfig(
        config=riva.client.RecognitionConfig(
            encoding=riva.client.AudioEncoding.LINEAR_PCM,
            language_code=args.language_code,
            max_alternatives=1,
            profanity_filter=args.profanity_filter,
            enable_automatic_punctuation=args.automatic_punctuation,
            verbatim_transcripts=not args.no_verbatim_transcripts,
            sample_rate_hertz=args.sample_rate_hz,
            audio_channel_count=1,
        ),
        interim_results=True,
    )
    riva.client.add_word_boosting_to_config(config, args.boosted_lm_words, args.boosted_lm_score)
    try:
        while True:
            transcript = None
            with riva.client.audio_io.MicrophoneStream(
                args.sample_rate_hz,
                args.file_streaming_chunk,
                device=args.input_device,
            ) as audio_chunk_iterator:
                responses=asr_service.streaming_response_generator(
                    audio_chunks=audio_chunk_iterator,
                    streaming_config=config,
                )
                speech_done = False
                while True:
                    response = next(responses) # process next chunk of audio
                    if not response.results:
                        continue
                    for result in response.results:
                        if not result.alternatives:
                            continue
                        if result.is_final:
                            transcript = result.alternatives[0].transcript
                            speech_done = True
                            break
                    if speech_done:
                        break
                line_out = transcript
                print(line_out)
                chatlog_file.write(line_out + "\n")
    except KeyboardInterrupt:
        chatlog_file.close()
        print("appended text to file specified.")
if __name__ == '__main__':
    main()
