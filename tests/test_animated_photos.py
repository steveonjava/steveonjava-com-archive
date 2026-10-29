"""Animated WebP policy of build.copy_photos. Synthetic fixtures only, in temporary directories."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build
from PIL import Image

UP = "wp-content/uploads/2014/01/"


def encode(image, fmt, **options):
    buffer = io.BytesIO()
    image.save(buffer, fmt, **options)
    return buffer.getvalue()


def copy(files):
    with tempfile.TemporaryDirectory(prefix="synthetic-animation-") as tmp:
        root, out = Path(tmp) / "root", Path(tmp) / "out"
        for rel, data in files.items():
            target = root / "assets" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        build.copy_photos(root, out)
        return {rel: (out / rel).read_bytes() for rel in files}


class AnimatedPhotoTests(unittest.TestCase):
    def setUp(self):
        self.frames = [Image.new("RGBA", (24, 16), color) for color in ("red", "lime", "blue")]
        exif = Image.Exif()
        exif[315] = "Synthetic metadata"
        self.moving = encode(self.frames[0], "WEBP", save_all=True, append_images=self.frames[1:], duration=[80, 90, 100], loop=0, lossless=True, exif=exif)
        with Image.open(io.BytesIO(self.moving)) as probe:
            self.assertIn("exif", probe.info, "the fixture must carry metadata for the metadata test to mean anything")

    def test_animated_webp_keeps_frames_timing_and_loop_and_loses_metadata(self):
        built = copy({UP + "moving.webp": self.moving})[UP + "moving.webp"]
        with Image.open(io.BytesIO(built)) as image:
            self.assertEqual((image.n_frames, image.is_animated, image.size), (3, True, (24, 16)))
            seen = []
            for index in range(image.n_frames):
                image.seek(index)
                seen.append((image.convert("RGBA").getpixel((0, 0)), image.info.get("duration")))
            self.assertEqual([p for p, _ in seen], [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)])
            self.assertEqual([d for _, d in seen], [80, 90, 100])
            self.assertEqual(image.info.get("loop"), 0)
            self.assertFalse(image.getexif())
            self.assertNotIn("exif", image.info)
        self.assertNotIn(b"EXIF", built)
        self.assertNotIn(b"Synthetic metadata", built)

    def test_second_pass_changes_nothing(self):
        once = copy({UP + "moving.webp": self.moving})[UP + "moving.webp"]
        twice = copy({UP + "moving.webp": once})[UP + "moving.webp"]
        with Image.open(io.BytesIO(once)) as a, Image.open(io.BytesIO(twice)) as b:
            self.assertEqual((a.n_frames, a.size), (b.n_frames, b.size))
            for index in range(a.n_frames):
                a.seek(index)
                b.seek(index)
                self.assertEqual(a.convert("RGBA").tobytes(), b.convert("RGBA").tobytes())
                self.assertEqual(a.info.get("duration"), b.info.get("duration"))

    def test_animated_png_is_rejected(self):
        first, second = Image.new("RGBA", (8, 8), "red"), Image.new("RGBA", (8, 8), "blue")
        data = encode(first, "PNG", save_all=True, append_images=[second], duration=[50, 50], loop=0)
        with self.assertRaisesRegex(ValueError, "Animated image"):
            copy({UP + "moving.png": data})

    def test_animated_webp_under_another_extension_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Animated image"):
            copy({UP + "moving-as-png.png": self.moving})

    def test_animated_gif_is_still_not_an_asset_type(self):
        first, second = Image.new("RGBA", (8, 8), "red"), Image.new("RGBA", (8, 8), "blue")
        data = encode(first, "GIF", save_all=True, append_images=[second], duration=[50, 50], loop=0)
        with self.assertRaisesRegex(ValueError, "Unexpected asset"):
            copy({UP + "moving.gif": data})

    def test_frame_bound_is_enforced(self):
        with patch.object(build, "MAX_ANIMATION_FRAMES", 2), self.assertRaisesRegex(ValueError, "Animation exceeds"):
            copy({UP + "moving.webp": self.moving})

    def test_pixel_bound_is_enforced_across_all_frames(self):
        with patch.object(build, "MAX_ANIMATION_PIXELS", 24 * 16 * 3 - 1), self.assertRaisesRegex(ValueError, "Animation exceeds"):
            copy({UP + "moving.webp": self.moving})
        with patch.object(build, "MAX_ANIMATION_PIXELS", 24 * 16 * 3):
            copy({UP + "moving.webp": self.moving})

    def test_static_images_are_unchanged(self):
        built = copy({UP + "still.webp": encode(self.frames[0], "WEBP", lossless=True),
                      UP + "photo.jpg": encode(self.frames[1].convert("RGB"), "JPEG")})
        with Image.open(io.BytesIO(built[UP + "still.webp"])) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertFalse(getattr(image, "is_animated", False))
        with Image.open(io.BytesIO(built[UP + "photo.jpg"])) as image:
            self.assertEqual((image.format, image.mode), ("JPEG", "RGB"))


if __name__ == "__main__":
    unittest.main()
