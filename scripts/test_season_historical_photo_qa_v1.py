from __future__ import annotations

import numpy as np

from scripts import season_historical_photo_qa_v1 as qa


class Recognizer:
    def alignCrop(self, image, face):
        return np.array([face[0]], dtype=np.float32)

    def feature(self, crop):
        return crop

    def match(self, reference, candidate, _metric):
        scores = {1: 0.18, 2: 0.68}
        return scores[int(candidate[0])]


def test_chooses_matching_face_even_when_another_is_larger(monkeypatch):
    reference = np.zeros((120, 120, 3), dtype=np.uint8)
    photo = np.zeros((700, 700, 3), dtype=np.uint8)
    wrong_large = np.array([1, 10, 240, 240] + [0] * 11, dtype=np.float32)
    right_small = np.array([2, 20, 100, 100] + [0] * 11, dtype=np.float32)
    monkeypatch.setattr(qa, "faces", lambda _detector, image: [np.array([99] + [0] * 14)] if image is reference else [wrong_large, right_small])
    face, detail = qa.matched_face(photo, reference, object(), Recognizer())
    assert face is right_small
    assert detail["photo_faces"] == 2
    assert detail["similarity"] == 0.68


def test_rejects_leg_sized_false_face(monkeypatch):
    reference = np.zeros((120, 120, 3), dtype=np.uint8)
    photo = np.zeros((700, 700, 3), dtype=np.uint8)
    tiny = np.array([2, 20, 40, 40] + [0] * 11, dtype=np.float32)
    monkeypatch.setattr(qa, "faces", lambda _detector, image: [np.array([99] + [0] * 14)] if image is reference else [tiny])
    face, detail = qa.matched_face(photo, reference, object(), Recognizer())
    assert face is None
    assert detail["reason"] == "face-too-small"


def test_tight_crop_rejects_edge():
    photo = np.zeros((100, 100, 3), dtype=np.uint8)
    face = np.array([0, 0, 75, 75] + [0] * 11, dtype=np.float32)
    assert qa.tight_crop(photo, face) is None
