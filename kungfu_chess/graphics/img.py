from __future__ import annotations

import pathlib
from turtle import color, delay, width

import cv2
import numpy as np



class Img:
    def __init__(self):
        self.img = None

    def read(self, path: str | pathlib.Path,
             size: tuple[int, int] | None = None,
             keep_aspect: bool = False,
             interpolation: int = cv2.INTER_AREA) -> "Img":
        """
        Load `path` into self.img and **optionally resize**.

        Parameters
        ----------
        path : str | Path
            Image file to load.
        size : (width, height) | None
            Target size in pixels.  If None, keep original.
        keep_aspect : bool
            • False  → resize exactly to `size`
            • True   → shrink so the *longer* side fits `size` while
                       preserving aspect ratio (no cropping).
        interpolation : OpenCV flag
            E.g.  `cv2.INTER_AREA` for shrink, `cv2.INTER_LINEAR` for enlarge.

        Returns
        -------
        Img
            `self`, so you can chain:  `sprite = Img().read("foo.png", (64,64))`
        """
        path = str(path)
        self.img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if self.img is None:
            raise FileNotFoundError(f"Cannot load image: {path}")

        if size is not None:
            target_w, target_h = size
            h, w = self.img.shape[:2]

            if keep_aspect:
                scale = min(target_w / w, target_h / h)
                new_w, new_h = int(w * scale), int(h * scale)
            else:
                new_w, new_h = target_w, target_h

            self.img = cv2.resize(self.img, (new_w, new_h), interpolation=interpolation)

        return self

    def copy(self) -> "Img":
        if self.img is None:
            raise ValueError("Image not loaded.")

        copied = Img()
        copied.img = self.img.copy()
        return copied

    @classmethod
    def blank(cls,
            width: int,
            height: int,
            color=(0, 0, 0, 255)) -> "Img":
        img = cls()
        if len(color) == 4:
            channels = 4
        else:
            channels = 3
        img.img = np.zeros((height, width, channels), dtype=np.uint8)
        img.img[:] = color
        return img

    @property
    def width(self) -> int:
        if self.img is None:
            raise ValueError("Image not loaded.")

        return self.img.shape[1]

    @property
    def height(self) -> int:
        if self.img is None:
            raise ValueError("Image not loaded.")

        return self.img.shape[0]
    
    def resize(self,
                width: int,
                height: int,
                keep_aspect: bool = False) -> "Img":
           if self.img is None:
                 raise ValueError("Image not loaded.")
           h, w = self.img.shape[:2]
           if keep_aspect:
                scale = min(width / w, height / h)
                width = int(w * scale)
                height = int(h * scale)
           self.img = cv2.resize(
                self.img,
                (width, height),
                interpolation=cv2.INTER_AREA,
           )

           return self

    def show_frame(self,
               window_name="KungFuChess",
               delay=1):
 
        if self.img is None:
            raise ValueError("Image not loaded.")

        cv2.imshow(window_name, self.img)
        cv2.waitKey(delay)
    @staticmethod
    def close(window_name="KungFuChess"):
        cv2.destroyWindow(window_name)

    @staticmethod
    def close_all():
         cv2.destroyAllWindows()

    @staticmethod
    def set_mouse_callback(window_name,
                       callback):
        cv2.setMouseCallback(window_name, callback)

    @staticmethod
    def is_window_open(window_name="KungFuChess") -> bool:
        return cv2.getWindowProperty(
            window_name,
            cv2.WND_PROP_VISIBLE,
        ) >= 1

    def draw_on(self, other_img, x, y):
        if self.img is None or other_img.img is None:
            raise ValueError("Both images must be loaded before drawing.")

        if self.img.shape[2] != other_img.img.shape[2]:
            if self.img.shape[2] == 3 and other_img.img.shape[2] == 4:
                self.img = cv2.cvtColor(self.img, cv2.COLOR_BGR2BGRA)
            elif self.img.shape[2] == 4 and other_img.img.shape[2] == 3:
                self.img = cv2.cvtColor(self.img, cv2.COLOR_BGRA2BGR)

        h, w = self.img.shape[:2]
        H, W = other_img.img.shape[:2]

        if y + h > H or x + w > W:
            raise ValueError("Logo does not fit at the specified position.")

        roi = other_img.img[y:y + h, x:x + w]

        if self.img.shape[2] == 4:
            b, g, r, a = cv2.split(self.img)
            mask = a / 255.0
            for c in range(3):
                roi[..., c] = (1 - mask) * roi[..., c] + mask * self.img[..., c]
        else:
            other_img.img[y:y + h, x:x + w] = self.img

    def put_text(self, txt, x, y, font_size, color=(255, 255, 255, 255), thickness=1):
        if self.img is None:
            raise ValueError("Image not loaded.")
        cv2.putText(self.img, txt, (x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, font_size,
                    color, thickness, cv2.LINE_AA)

    def show(self):
        if self.img is None:
            raise ValueError("Image not loaded.")
        cv2.imshow("Image", self.img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()