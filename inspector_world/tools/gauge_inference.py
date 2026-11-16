#!/usr/bin/env python3
"""Run the trained gauge locator and distribution reader on one image.

The current checkpoints locate one target gauge and read its normalized needle
position. Instrument classification is intentionally kept outside this module
until the four-class detector is trained. For now the caller supplies P-01,
P-02, T-01 or V-01.
"""

import argparse
import json
import math
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import torch
import torch.nn.functional as functional
from PIL import Image, ImageDraw
from torchvision import models, transforms


INSTRUMENTS: Dict[str, Dict[str, object]] = {
    "P-01": {
        "instrument_type": "pressure",
        "unit": "МПа",
        "min_value": 0.0,
        "max_value": 1.6,
        "norm_lo": 0.2,
        "norm_hi": 1.0,
    },
    "P-02": {
        "instrument_type": "pressure",
        "unit": "бар",
        "min_value": 0.0,
        "max_value": 10.0,
        "norm_lo": 1.0,
        "norm_hi": 6.0,
    },
    "T-01": {
        "instrument_type": "temperature",
        "unit": "°C",
        "min_value": 0.0,
        "max_value": 120.0,
        "norm_lo": 10.0,
        "norm_hi": 80.0,
    },
    "V-01": {
        "instrument_type": "vacuum",
        "unit": "МПа",
        "min_value": -0.1,
        "max_value": 0.0,
        "norm_lo": -0.08,
        "norm_hi": -0.02,
    },
}

NUMBER_OF_BINS = 101
FULL_IMAGE_SIZE = 320
READER_IMAGE_SIZE = 224
NORMALIZE_MEAN = [0.485, 0.456, 0.406]
NORMALIZE_STD = [0.229, 0.224, 0.225]

FULL_TRANSFORM = transforms.Compose(
    [
        transforms.Resize((FULL_IMAGE_SIZE, FULL_IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=NORMALIZE_MEAN, std=NORMALIZE_STD),
    ]
)

READER_TRANSFORM = transforms.Compose(
    [
        transforms.Resize((READER_IMAGE_SIZE, READER_IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=NORMALIZE_MEAN, std=NORMALIZE_STD),
    ]
)


@dataclass
class GaugeReading:
    instrument_code: str
    instrument_type: str
    value: float
    unit: str
    normalized_value: float
    status: str
    confidence: float
    needs_retake: bool
    box: Tuple[int, int, int, int]
    image_path: str


def normalized_to_value(instrument_code: str, normalized_value: float) -> float:
    spec = INSTRUMENTS[instrument_code]
    minimum = float(spec["min_value"])
    maximum = float(spec["max_value"])
    return minimum + normalized_value * (maximum - minimum)


def value_status(instrument_code: str, value: float) -> str:
    spec = INSTRUMENTS[instrument_code]
    return (
        "OK"
        if float(spec["norm_lo"]) <= value <= float(spec["norm_hi"])
        else "ALARM"
    )


def build_locator() -> torch.nn.Module:
    model = models.resnet18(weights=None)
    input_features = model.fc.in_features
    model.fc = torch.nn.Sequential(
        torch.nn.Dropout(p=0.20),
        torch.nn.Linear(input_features, 4),
        torch.nn.Sigmoid(),
    )
    return model


def build_reader() -> torch.nn.Module:
    model = models.resnet18(weights=None)
    input_features = model.fc.in_features
    model.fc = torch.nn.Sequential(
        torch.nn.Dropout(p=0.10),
        torch.nn.Linear(input_features, NUMBER_OF_BINS),
    )
    return model


def _load_weights(model: torch.nn.Module, path: str, device: torch.device) -> None:
    weights = torch.load(path, map_location=device, weights_only=True)
    model.load_state_dict(weights)
    model.to(device)
    model.eval()


def _box_from_prediction(
    prediction: torch.Tensor, image: Image.Image
) -> Tuple[float, float, float, float]:
    center_x, center_y, box_width, box_height = prediction.tolist()
    image_width, image_height = image.size
    return (
        (center_x - box_width / 2.0) * image_width,
        (center_y - box_height / 2.0) * image_height,
        (center_x + box_width / 2.0) * image_width,
        (center_y + box_height / 2.0) * image_height,
    )


def expand_and_crop(
    image: Image.Image,
    box: Tuple[float, float, float, float],
    padding: float = 0.35,
) -> Image.Image:
    x0, y0, x1, y1 = box
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    crop_box = (
        max(0, int(x0 - width * padding)),
        max(0, int(y0 - height * padding)),
        min(image.width, int(x1 + width * padding)),
        min(image.height, int(y1 + height * padding)),
    )
    if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
        raise ValueError("locator produced an invalid crop")
    return image.crop(crop_box)


def distribution_result(logits: torch.Tensor) -> Tuple[float, float]:
    """Return expected needle position and an entropy-based confidence score."""
    probabilities = functional.softmax(logits, dim=1)[0]
    bin_values = torch.linspace(0.0, 1.0, NUMBER_OF_BINS, device=logits.device)
    normalized_value = float((probabilities * bin_values).sum().item())
    entropy = float(
        (-(probabilities * probabilities.clamp_min(1e-12).log()).sum()).item()
    )
    confidence = 1.0 - entropy / math.log(NUMBER_OF_BINS)
    return max(0.0, min(1.0, normalized_value)), max(0.0, min(1.0, confidence))


class GaugeInference:
    def __init__(
        self,
        locator_path: str,
        reader_path: str,
        device_name: Optional[str] = None,
    ):
        if device_name:
            self.device = torch.device(device_name)
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.locator = build_locator()
        self.reader = build_reader()
        _load_weights(self.locator, locator_path, self.device)
        _load_weights(self.reader, reader_path, self.device)

    @torch.inference_mode()
    def predict(
        self,
        image_path: str,
        instrument_code: str,
        retake_threshold: float = 0.10,
    ) -> GaugeReading:
        if instrument_code not in INSTRUMENTS:
            raise ValueError("unknown instrument: %s" % instrument_code)
        image = Image.open(image_path).convert("RGB")
        locator_input = FULL_TRANSFORM(image).unsqueeze(0).to(self.device)
        raw_box = _box_from_prediction(self.locator(locator_input)[0].cpu(), image)
        crop = expand_and_crop(image, raw_box)
        reader_input = READER_TRANSFORM(crop).unsqueeze(0).to(self.device)
        normalized_value, confidence = distribution_result(self.reader(reader_input))
        value = normalized_to_value(instrument_code, normalized_value)
        spec = INSTRUMENTS[instrument_code]
        clipped_box = (
            max(0, int(raw_box[0])),
            max(0, int(raw_box[1])),
            min(image.width, int(raw_box[2])),
            min(image.height, int(raw_box[3])),
        )
        return GaugeReading(
            instrument_code=instrument_code,
            instrument_type=str(spec["instrument_type"]),
            value=value,
            unit=str(spec["unit"]),
            normalized_value=normalized_value,
            status=value_status(instrument_code, value),
            confidence=confidence,
            needs_retake=confidence < retake_threshold,
            box=clipped_box,
            image_path=os.path.abspath(image_path),
        )


def save_annotated(image_path: str, reading: GaugeReading, output_path: str) -> None:
    image = Image.open(image_path).convert("RGB")
    drawer = ImageDraw.Draw(image)
    color = "#25b34b" if reading.status == "OK" else "#e53935"
    drawer.rectangle(reading.box, outline=color, width=4)
    drawer.text(
        (reading.box[0], max(0, reading.box[1] - 18)),
        "%s: %.3f %s | %s"
        % (reading.instrument_code, reading.value, reading.unit, reading.status),
        fill=color,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Read one analog gauge image")
    parser.add_argument("--image", required=True)
    parser.add_argument("--instrument", required=True, choices=sorted(INSTRUMENTS))
    parser.add_argument("--locator", required=True)
    parser.add_argument("--reader", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--retake-threshold", type=float, default=0.10)
    parser.add_argument("--json-out")
    parser.add_argument("--annotated-out")
    args = parser.parse_args()

    inference = GaugeInference(args.locator, args.reader, args.device)
    result = inference.predict(args.image, args.instrument, args.retake_threshold)
    payload = asdict(result)
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.json_out:
        destination = Path(args.json_out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.annotated_out:
        save_annotated(args.image, result, args.annotated_out)


if __name__ == "__main__":
    main()
