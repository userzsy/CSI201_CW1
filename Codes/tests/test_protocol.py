"""Test the protocol shared by both entry points at the byte-stream boundary."""


# Imports and Test Setup

import struct
import unittest

from quizlib.protocol import (FrameBuffer, FrameSizeError, MAX_PAYLOAD, MessageType as M, ProtocolError,
                              decode_frame, encode_frame, error, event, request, response)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.message = request(M.LOGIN_REQUEST, {"user_id": "1", "name": "中文"}, request_id="r1")

    # Encoding and TCP Fragment Boundaries

    def test_round_trip_and_byte_length(self):
        frame = encode_frame(self.message)
        self.assertEqual(struct.unpack("!I", frame[:4])[0], len(frame[4:]))
        self.assertEqual(decode_frame(frame), self.message)

    def test_every_fragment_boundary(self):
        frame = encode_frame(self.message)
        for split in range(1, len(frame)):
            with self.subTest(split=split):
                buffer = FrameBuffer()
                self.assertEqual(list(buffer.feed(frame[:split])), [])
                self.assertEqual(list(buffer.feed(frame[split:])), [self.message])

    def test_bytewise_and_coalesced_order(self):
        messages = [request(M.LIST_ROOMS_REQUEST, request_id=f"r{i}") for i in range(3)]
        frames = b"".join(map(encode_frame, messages))
        buffer = FrameBuffer()
        found = []
        for value in frames:
            found.extend(buffer.feed(bytes([value])))
        self.assertEqual(found, messages)
        self.assertEqual(list(FrameBuffer().feed(frames)), messages)

    # Invalid Frames and Envelopes

    def test_invalid_lengths_rejected_from_header(self):
        for length in (0, MAX_PAYLOAD + 1, 2**32 - 1):
            with self.subTest(length=length), self.assertRaises(ProtocolError):
                list(FrameBuffer().feed(struct.pack("!I", length)))

    def test_bad_payloads(self):
        for payload in (b"\xff", b"{", b"[]", b"null", b"NaN", b'{"version":NaN}'):
            with self.subTest(payload=payload), self.assertRaises(ProtocolError):
                decode_frame(struct.pack("!I", len(payload)) + payload)

    def test_missing_fields(self):
        for key in self.message:
            message = dict(self.message)
            del message[key]
            with self.subTest(key=key), self.assertRaises(ProtocolError):
                encode_frame(message)

    def test_wrong_envelope_values(self):
        for key, value in (("version", True), ("version", 2), ("type", []), ("type", "UNKNOWN"),
                           ("payload", []), ("request_id", None), ("request_id", 3),
                           ("event_id", "bad"), ("session_id", "")):
            with self.subTest(key=key, value=value), self.assertRaises(ProtocolError):
                encode_frame(dict(self.message, **{key: value}))

    # Correlation and Decoder Edge Cases

    def test_events_and_response_correlation(self):
        a = event(M.QUESTION_EVENT, "sid", {})
        b = event(M.QUESTION_EVENT, "sid", {})
        self.assertNotEqual(a["event_id"], b["event_id"])
        self.assertIsNone(a["request_id"])
        self.assertEqual(response(M.LOGIN_RESPONSE, "r1", "sid", {})["request_id"], "r1")
        self.assertIsNone(error(None, None, "INVALID_MESSAGE", "bad")["event_id"])

    def test_decode_requires_exactly_one_complete_frame(self):
        frame = encode_frame(self.message)
        for data in (frame[:-1], frame + b"x", frame + frame):
            with self.subTest(length=len(data)), self.assertRaises(ProtocolError):
                decode_frame(data)

    def test_valid_frame_before_bad_frame_is_preserved(self):
        stream = FrameBuffer().feed(encode_frame(self.message) + b"\0\0\0\0")
        self.assertEqual(next(stream), self.message)
        with self.assertRaises(ProtocolError):
            next(stream)

    def test_nonstandard_numbers_and_oversized_encoding(self):
        for payload in ({"x": float("nan")}, {"x": "a" * MAX_PAYLOAD}):
            with self.assertRaises(ProtocolError):
                encode_frame(request(M.LOGIN_REQUEST, payload))

    def test_unpaired_surrogate_encoding_is_a_protocol_error(self):
        for value in ("\ud800", "\udfff"):
            with self.subTest(value=ascii(value)), self.assertRaises(ProtocolError):
                encode_frame(request(M.LOGIN_REQUEST, {"name": value}))

    def test_chinese_and_supplementary_unicode_round_trip(self):
        for value in ("中文 English", "😀", "\U00010437"):
            with self.subTest(value=value):
                message = request(M.LOGIN_REQUEST, {"name": value})
                self.assertEqual(decode_frame(encode_frame(message)), message)

    def test_size_error_is_distinct_from_invalid_utf8_encoding(self):
        with self.assertRaises(FrameSizeError):
            encode_frame(request(M.LOGIN_REQUEST, {"name": "x" * MAX_PAYLOAD}))
        with self.assertRaises(ProtocolError) as failure:
            encode_frame(request(M.LOGIN_REQUEST, {"name": "\ud800"}))
        self.assertNotIsInstance(failure.exception, FrameSizeError)
