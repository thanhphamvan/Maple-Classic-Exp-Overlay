"""TextOCR with Tesseract, reading each image as one line of text (--psm 7).

Starting Tesseract (and loading its language data) costs about 40 ms, more than reading a
short line, so read_lines() hands it all of its images in one run: a list of image files,
read one after the other. The text of each comes back exactly as if it had been run on that
image alone; reading a map name's or class's 6 tries that way costs about a quarter of the
CPU. Its own threads are off (OMP_THREAD_LIMIT=1): for a few small lines they only cost CPU.
"""
import os
import subprocess
import tempfile

import cv2

from .base import TextOCR

PAGE_BREAK = "\f"                    # what Tesseract puts between the images' texts


class TesseractError(RuntimeError):
    pass


class TesseractOCR(TextOCR):
    name = "tesseract"

    def __init__(self, cmd, timeout=30):
        """cmd: the full path of the tesseract program to run."""
        self.cmd, self.timeout = cmd, timeout
        self.env = dict(os.environ, OMP_THREAD_LIMIT="1")
        self.runs = 0                                   # how many times Tesseract was started

    def read_line(self, image, chars=None):
        return self.read_lines([image], chars)[0]

    def read_lines(self, images, chars=None):
        if not images:
            return []
        with tempfile.TemporaryDirectory(prefix="maple-exp-ocr-") as folder:
            names = []
            for i, image in enumerate(images):
                name = os.path.join(folder, f"{i}.png")
                ok, png = cv2.imencode(".png", image)  # (cv2.imwrite can't take every Windows path)
                if not ok:
                    raise TesseractError("couldn't save an image for Tesseract")
                with open(name, "wb") as f:
                    f.write(png.tobytes())
                names.append(name)
            listing = os.path.join(folder, "images.txt")
            with open(listing, "w", encoding="utf-8") as f:
                f.write("\n".join(names) + "\n")
            args = [self.cmd, listing, "stdout", "--psm", "7"]
            if chars:
                args += ["-c", f"tessedit_char_whitelist={chars}"]
            self.runs += 1
            run = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL, env=self.env,
                                 timeout=self.timeout, **_hidden())
        if run.returncode != 0:
            raise TesseractError(run.stderr.decode("utf-8", "replace").strip()[-500:] or f"exit code {run.returncode}")
        texts = run.stdout.decode("utf-8", "replace").split(PAGE_BREAK)
        if len(texts) == len(images) + 1 and not texts[-1].strip():
            texts.pop()                                 # (a page break after the last one too)
        if len(texts) != len(images):
            raise TesseractError(f"Tesseract read {len(texts)} images of {len(images)}")
        return texts


def _hidden():
    """On Windows, no console window flashing up each time it runs."""
    if not hasattr(subprocess, "STARTUPINFO"):
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": info}
