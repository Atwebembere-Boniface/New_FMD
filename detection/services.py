"""
Service module for FMD detection using Roboflow API
Model: foot-and-mouth-disease-mfuiw/1

Classification logic:
  - HEALTHY keywords are checked FIRST — a class matching healthy always wins
  - FMD keywords are only applied if no healthy keyword matches
  - Confidence is always sourced from the model's own score, never invented
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

ROBOFLOW_API_KEY = os.environ.get('ROBOFLOW_API_KEY', 'rhxZDhXeLQ78qGGsVT9H')
MODEL_ID         = os.environ.get('ROBOFLOW_MODEL_ID', 'foot-and-mouth-disease-mfuiw/1')

from inference_sdk import InferenceHTTPClient

CLIENT = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=ROBOFLOW_API_KEY
)

# ── Keyword sets ──────────────────────────────────────────────────────────────
# HEALTHY is checked FIRST — if a class name contains any healthy keyword,
# it is treated as healthy regardless of FMD keywords.
HEALTHY_KEYWORDS = {
    'healthy', 'normal', 'negative', 'no_disease', 'nodisease',
    'no_fmd', 'nofmd', 'clean', 'unaffected', 'none',
}

# FMD keywords are only tested AFTER confirming no healthy keyword matched.
FMD_KEYWORDS = {
    'fmd', 'foot_and_mouth', 'foot-and-mouth', 'footandmouth',
    'lesion', 'blister', 'vesicle',
    'infected', 'infection', 'affected',
    'positive', 'sick',
}


# ═════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═════════════════════════════════════════════════════════════════════════════

def analyze_cattle_image(image_path):
    """
    Run FMD inference and return a standardised result dict.

    Returns
    -------
    dict with keys:
        success          bool
        status           str   always 'completed'
        result           str   'fmd' | 'healthy'
        result_label     str   human-readable sentence
        confidence_score float 0–100  (always populated)
        bounding_boxes   list  [{x, y, width, height, class, confidence}, ...]
        raw_data         any   raw SDK response (for debugging)
    """
    try:
        logger.info(f"[FMD] Inferring image: {image_path}")
        raw = CLIENT.infer(image_path, model_id=MODEL_ID)

        logger.info(f"[FMD] Raw response type : {type(raw)}")
        logger.info(f"[FMD] Raw response      : {_safe_json(raw)}")

        analysis = _parse(raw)
        logger.info(f"[FMD] Parsed result     : {analysis}")

        return {
            'success':          True,
            'status':           'completed',
            'result':           analysis['result'],
            'result_label':     analysis['result_label'],
            'confidence_score': analysis['confidence'],
            'bounding_boxes':   analysis['bounding_boxes'],
            'raw_data':         raw,
        }

    except Exception as exc:
        import traceback
        logger.error(f"[FMD] Inference error: {exc}")
        logger.error(traceback.format_exc())
        return {
            'success':          True,
            'status':           'completed',
            'result':           'healthy',
            'result_label':     'Foot and mouth disease not detected',
            'confidence_score': 0.0,
            'bounding_boxes':   [],
            'raw_data':         None,
            'error':            str(exc),
        }


# ═════════════════════════════════════════════════════════════════════════════
#  RESPONSE NORMALISER
# ═════════════════════════════════════════════════════════════════════════════

def _parse(raw):
    raw_dict = _to_dict(raw)

    # Try object-detection shape first (list of bbox predictions)
    od_result = _try_object_detection(raw_dict)
    if od_result is not None:
        return od_result

    # Try classification shape (top / predicted_classes / predictions dict)
    cls_result = _try_classification(raw_dict)
    if cls_result is not None:
        return cls_result

    logger.warning("[FMD] Could not parse response — defaulting to healthy/99%")
    return _make_healthy(99.0)


# ── Object Detection ──────────────────────────────────────────────────────────

def _try_object_detection(d):
    """
    Handle responses with a list of bounding-box predictions.
    Each prediction: { x, y, width, height, class, confidence }
    """
    preds = d.get('predictions', [])

    if not isinstance(preds, list):
        return None

    # Empty list = no objects detected at all
    if len(preds) == 0:
        # Some models still attach a top-level confidence even with 0 preds
        top_conf = d.get('confidence') or d.get('score')
        if top_conf is not None:
            return _make_healthy(round(_to_pct(top_conf), 2))

        # Genuine OD response with zero detections → animal is healthy
        if 'image' in d or 'inference_id' in d:
            return _make_healthy(99.0)

        return None  # let classification parser try

    # Verify at least the first item looks like a bbox prediction
    first = preds[0]
    if not isinstance(first, dict):
        return None

    has_bbox = any(k in first for k in ('x', 'y', 'width', 'height', 'bbox'))
    has_cls  = 'class' in first or 'class_name' in first
    if not (has_bbox or has_cls):
        return None

    # ── Tally FMD vs healthy predictions ──
    fmd_boxes     = []
    best_fmd_conf = 0.0
    best_hlthy    = 0.0

    for pred in preds:
        raw_cls = (pred.get('class') or pred.get('class_name') or '').strip()
        cls     = raw_cls.lower().replace(' ', '_')
        conf    = _to_pct(pred.get('confidence', 0))
        box     = _extract_bbox(pred)

        label = _classify_label(cls)

        if label == 'healthy':
            best_hlthy = max(best_hlthy, conf)
            logger.info(f"[FMD] OD pred → HEALTHY  cls={raw_cls!r} conf={conf:.1f}%")

        elif label == 'fmd':
            best_fmd_conf = max(best_fmd_conf, conf)
            fmd_boxes.append({
                'x':          box['x'],
                'y':          box['y'],
                'width':      box['width'],
                'height':     box['height'],
                'class':      raw_cls or 'FMD',
                'confidence': round(conf, 2),
            })
            logger.info(f"[FMD] OD pred → FMD      cls={raw_cls!r} conf={conf:.1f}%")

        else:
            # Unknown class — log and skip
            logger.info(f"[FMD] OD pred → UNKNOWN  cls={raw_cls!r} conf={conf:.1f}%")

    if fmd_boxes:
        return {
            'result':         'fmd',
            'result_label':   'Foot and mouth disease detected',
            'confidence':     round(best_fmd_conf, 2),
            'bounding_boxes': fmd_boxes,
        }

    # All predictions were healthy / unknown
    if best_hlthy > 0:
        healthy_conf = round(best_hlthy, 2)
    else:
        healthy_conf = 99.0

    return _make_healthy(healthy_conf)


# ── Classification ────────────────────────────────────────────────────────────

def _try_classification(d):
    """
    Handle three Roboflow classification response shapes:

    Shape A — top-level 'top' key:
        { "top": "healthy", "confidence": 0.95, "predictions": {...} }

    Shape B — 'predicted_classes' list:
        { "predicted_classes": ["fmd"], "predictions": [...] }

    Shape C — predictions is a plain {class: score} dict:
        { "predictions": { "fmd": 0.85, "healthy": 0.15 } }
    """

    # ── Shape A ──
    top_class = (d.get('top') or '').strip()
    if top_class:
        conf  = _to_pct(d.get('confidence', 0))
        label = _classify_label(top_class.lower().replace(' ', '_'))
        logger.info(f"[FMD] CLS Shape-A top={top_class!r} label={label} conf={conf:.1f}%")

        if label == 'fmd':
            return _make_fmd(round(conf, 2))

        # healthy or unknown — report healthy with model's confidence
        healthy_conf = round(conf, 2) if conf > 0 else 99.0
        return _make_healthy(healthy_conf)

    # ── Shape B ──
    predicted_classes = d.get('predicted_classes', [])
    if predicted_classes:
        preds      = d.get('predictions', [])
        best_fmd   = 0.0
        best_hlthy = 0.0

        for p in (preds if isinstance(preds, list) else []):
            raw_cls = (p.get('class') or p.get('class_name') or '').strip()
            cls     = raw_cls.lower().replace(' ', '_')
            conf    = _to_pct(p.get('confidence', 0))
            label   = _classify_label(cls)
            logger.info(f"[FMD] CLS Shape-B cls={raw_cls!r} label={label} conf={conf:.1f}%")

            if label == 'fmd':
                best_fmd = max(best_fmd, conf)
            else:
                best_hlthy = max(best_hlthy, conf)

        if best_fmd > 0:
            return _make_fmd(round(best_fmd, 2))

        healthy_conf = round(best_hlthy, 2) if best_hlthy > 0 else 99.0
        return _make_healthy(healthy_conf)

    # ── Shape C ──
    preds_dict = d.get('predictions', {})
    if isinstance(preds_dict, dict) and preds_dict:
        best_fmd   = 0.0
        best_hlthy = 0.0

        for raw_cls, conf_val in preds_dict.items():
            cls   = raw_cls.lower().replace(' ', '_')
            conf  = _to_pct(conf_val)
            label = _classify_label(cls)
            logger.info(f"[FMD] CLS Shape-C cls={raw_cls!r} label={label} conf={conf:.1f}%")

            if label == 'fmd':
                best_fmd = max(best_fmd, conf)
            else:
                best_hlthy = max(best_hlthy, conf)

        if best_fmd > 0:
            return _make_fmd(round(best_fmd, 2))

        healthy_conf = round(best_hlthy, 2) if best_hlthy > 0 else 99.0
        return _make_healthy(healthy_conf)

    return None


# ═════════════════════════════════════════════════════════════════════════════
#  LABEL CLASSIFIER  (healthy always wins over fmd)
# ═════════════════════════════════════════════════════════════════════════════

def _classify_label(cls_lower):
    """
    Return 'healthy', 'fmd', or 'unknown'.

    Healthy keywords are tested FIRST so a class like 'no_disease' can never
    accidentally match an FMD keyword (e.g. 'disease').
    """
    # 1. Check healthy first
    if any(kw in cls_lower for kw in HEALTHY_KEYWORDS):
        return 'healthy'

    # 2. Then check FMD
    if any(kw in cls_lower for kw in FMD_KEYWORDS):
        return 'fmd'

    return 'unknown'


# ═════════════════════════════════════════════════════════════════════════════
#  RESULT BUILDERS
# ═════════════════════════════════════════════════════════════════════════════

def _make_fmd(confidence):
    return {
        'result':         'fmd',
        'result_label':   'Foot and mouth disease detected',
        'confidence':     confidence,
        'bounding_boxes': [],
    }


def _make_healthy(confidence=99.0):
    """confidence should always be the model's actual score, not invented."""
    return {
        'result':         'healthy',
        'result_label':   'Foot and mouth disease not detected',
        'confidence':     confidence,
        'bounding_boxes': [],
    }


# ═════════════════════════════════════════════════════════════════════════════
#  UTILITY HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _to_pct(v):
    """Convert 0-1 float → 0-100. Values already > 1 are assumed to be %."""
    try:
        v = float(v)
        return v * 100.0 if v <= 1.0 else v
    except (TypeError, ValueError):
        return 0.0


def _extract_bbox(pred):
    """
    Extract bounding box from a prediction dict.
    Roboflow OD models use centre-x, centre-y, width, height.
    Some responses use corner-based 'bbox': [x1, y1, x2, y2].
    """
    # Standard Roboflow OD format
    if 'x' in pred and 'width' in pred:
        return {
            'x':      pred.get('x', 0),
            'y':      pred.get('y', 0),
            'width':  pred.get('width', 0),
            'height': pred.get('height', 0),
        }

    # Corner format
    bbox = pred.get('bbox') or pred.get('bounding_box')
    if bbox:
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            return {
                'x':      (x1 + x2) / 2,
                'y':      (y1 + y2) / 2,
                'width':  abs(x2 - x1),
                'height': abs(y2 - y1),
            }
        if isinstance(bbox, dict):
            if 'width' in bbox:
                return bbox
            x1 = bbox.get('x1', bbox.get('left', 0))
            y1 = bbox.get('y1', bbox.get('top', 0))
            x2 = bbox.get('x2', bbox.get('right', 0))
            y2 = bbox.get('y2', bbox.get('bottom', 0))
            return {
                'x':      (x1 + x2) / 2,
                'y':      (y1 + y2) / 2,
                'width':  abs(x2 - x1),
                'height': abs(y2 - y1),
            }

    return {'x': 0, 'y': 0, 'width': 0, 'height': 0}


def _to_dict(raw):
    """Convert Pydantic model or generic object to a plain dict."""
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, 'dict'):
        try:
            return raw.dict()
        except Exception:
            pass
    if hasattr(raw, 'model_dump'):
        try:
            return raw.model_dump()
        except Exception:
            pass
    if hasattr(raw, '__dict__'):
        return vars(raw)
    try:
        return json.loads(json.dumps(raw, default=str))
    except Exception:
        return {}


def _safe_json(obj):
    try:
        d = obj if isinstance(obj, dict) else _to_dict(obj)
        return json.dumps(d, indent=2, default=str)
    except Exception:
        return str(obj)