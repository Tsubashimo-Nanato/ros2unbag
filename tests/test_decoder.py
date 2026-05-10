from __future__ import annotations

import dataclasses
import unittest

from ros2_unbag.core.decoder import decode_sensor_image, flatten_message, message_to_plain


@dataclasses.dataclass
class Nested:
    value: float


@dataclasses.dataclass
class FakeMessage:
    name: str
    nested: Nested
    small_array: list[int]
    large_array: list[int]
    empty_array: list[int] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class FakeImage:
    height: int
    width: int
    encoding: str
    step: int
    data: bytes


class DecoderTests(unittest.TestCase):
    def test_flatten_nested_message(self) -> None:
        message = FakeMessage("demo", Nested(1.5), [1, 2], list(range(20)))
        flattened = flatten_message(message)

        self.assertEqual(flattened["name"], "demo")
        self.assertEqual(flattened["nested.value"], 1.5)
        self.assertEqual(flattened["small_array.0"], 1)
        self.assertIn("large_array", flattened)
        self.assertEqual(flattened["empty_array"], "[]")

    def test_bytes_are_preserved_as_base64(self) -> None:
        data = message_to_plain({"payload": b"abc"})
        self.assertEqual(data["payload"]["byte_length"], 3)
        self.assertEqual(data["payload"]["data"], "YWJj")

    def test_decode_mono8_sensor_image(self) -> None:
        image = FakeImage(height=2, width=2, encoding="mono8", step=2, data=bytes([0, 255, 1, 0]))

        frame = decode_sensor_image(image)

        self.assertEqual(frame.width, 2)
        self.assertEqual(frame.height, 2)
        self.assertEqual(frame.array.tolist(), [[0, 255], [1, 0]])

    def test_decode_rgb8_sensor_image_to_opencv_bgr(self) -> None:
        image = FakeImage(height=1, width=1, encoding="rgb8", step=3, data=bytes([255, 0, 0]))

        frame = decode_sensor_image(image)

        self.assertEqual(frame.array.tolist(), [[[0, 0, 255]]])


if __name__ == "__main__":
    unittest.main()
