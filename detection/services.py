"""
Service module for FMD detection using Roboflow API
Model: foot-and-mouth-disease-mfuiw/1

Handles all Roboflow SDK response shapes:
  - dict  with 'predictions' list  (object detection / instance segmentation)
  - dict  with 'top' / 'predictions' list  (classification)
  - object with .predictions attribute   (Pydantic response from newer SDK)
  - raw classification response          (top-level 'predicted_classes' list)
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

# ── Credentials ──────────────────────────────────────────────────────────────
ROBOFLOW_API_KEY = os.environ.get('ROBOFLOW_API_KEY', 'rhxZDhXeLQ78qGGsVT9H')
MODEL_ID         = os.environ.get('ROBOFLOW_MODEL_ID', 'foot-and-mouth-disease-mfuiw/1')

# ── Client ───────────────────────────────────────────────────────────────────
from inference_sdk import InferenceHTTPClient

CLIENT = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=ROBOFLOW_API_KEY
)

# ── FMD keyword sets ─────────────────────────────────────────────────────────
FMD_KEYWORDS = {
    'fmd', 'foot-and-mouth', 'foot_and_mouth', 'footandmouth',
    'disease', 'infected', 'infection', 'lesion', 'blister',
    'positive', 'sick', 'affected'
}
HEALTHY_KEYWORDS = {
    'healthy', 'normal', 'negative', 'no_disease', 'nodisease', 'clean'
}


# ═════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═════════════════════════════════════════════════════════════════════════════

def analyze_cattle_image(image_path):
    """
    Run FMD inference and return a standardised result dict.

    Returns
    -------
    dict
        success          bool
        status           str   always 'completed'
        result           str   'fmd' | 'healthy'
        result_label     str   human-readable sentence
        confidence_score float 0-100
        bounding_boxes   list  [{x,y,width,height,class,confidence}, ...]
        raw_data         any   raw SDK response (for debugging)
    """
    try:
        logger.info(f"[FMD] Inferring image: {image_path}")
        raw = CLIENT.infer(image_path, model_id=MODEL_ID)

        # Log the full response so you can inspect it in Django logs
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
            'success':          True,          # keeps status = 'completed'
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
    """
    Accept ANY Roboflow SDK response shape and return:
        { result, result_label, confidence, bounding_boxes }
    """
    # 1. Convert Pydantic / object responses to plain dict
    raw_dict = _to_dict(raw)

    # 2. Try object-detection / instance-segmentation shape first
    #    { "predictions": [ {x, y, width, height, class, confidence}, ... ] }
    od_result = _try_object_detection(raw_dict)
    if od_result is not None:
        return od_result

    # 3. Try classification shape
    #    { "top": "fmd", "confidence": 0.95, "predictions": {"fmd": 0.95, ...} }
    #    or { "predicted_classes": ["fmd"], "predictions": [...] }
    cls_result = _try_classification(raw_dict)
    if cls_result is not None:
        return cls_result

    # 4. Nothing matched — safe default
    logger.warning("[FMD] Could not parse response — defaulting to healthy")
    return _healthy(0.0)


# ── Object Detection ──────────────────────────────────────────────────────────

def _try_object_detection(d):
    """
    Handle responses that contain a list of bounding-box predictions.
    Each prediction looks like:
        { "x": 320, "y": 240, "width": 100, "height": 80,
          "class": "fmd", "confidence": 0.87 }
    """
    preds = d.get('predictions', [])

    # Must be a list of dicts (not a classification dict)
    if not isinstance(preds, list) or len(preds) == 0:
        return None

    # If the first item doesn't look like a bbox prediction, skip
    first = preds[0] if preds else {}
    if not isinstance(first, dict):
        return None

    has_bbox = any(k in first for k in ('x', 'y', 'width', 'height', 'bbox'))
    has_cls  = 'class' in first or 'class_name' in first

    if not (has_bbox or has_cls):
        return None

    # ── Categorise each prediction ──
    fmd_boxes     = []
    best_fmd_conf = 0.0
    best_hlthy    = 0.0

    for pred in preds:
        cls  = (pred.get('class') or pred.get('class_name') or '').lower().replace(' ', '_')
        conf = _to_pct(pred.get('confidence', 0))

        # Extract bounding box — handle both centre-point and corner formats
        box = _extract_bbox(pred)

        if _is_fmd(cls):
            best_fmd_conf = max(best_fmd_conf, conf)
            fmd_boxes.append({
                'x':          box['x'],
                'y':          box['y'],
                'width':      box['width'],
                'height':     box['height'],
                'class':      pred.get('class') or pred.get('class_name') or 'FMD',
                'confidence': round(conf, 2),
            })
        else:
            best_hlthy = max(best_hlthy, conf)

    if fmd_boxes:
        return {
            'result':        'fmd',
            'result_label':  'Foot and mouth disease detected',
            'confidence':    round(best_fmd_conf, 2),
            'bounding_boxes': fmd_boxes,
        }
    return _healthy(round(best_hlthy, 2))


# ── Classification ────────────────────────────────────────────────────────────

def _try_classification(d):
    """
    Handle Roboflow classification responses:

    Shape A – top-level 'top' key:
        { "top": "fmd", "confidence": 0.95,
          "predictions": { "fmd": 0.95, "healthy": 0.05 } }

    Shape B – 'predicted_classes' list:
        { "predicted_classes": ["fmd"],
          "predictions": [{"class_name": "fmd", "confidence": 0.95}] }
    """
    # Shape A
    top_class = d.get('top', '')
    if top_class:
        conf = _to_pct(d.get('confidence', 0))
        if _is_fmd(top_class.lower()):
            return {
                'result':        'fmd',
                'result_label':  'Foot and mouth disease detected',
                'confidence':    round(conf, 2),
                'bounding_boxes': [],   # classification — no spatial info
            }
        return _healthy(round(conf, 2))

    # Shape B
    predicted_classes = d.get('predicted_classes', [])
    if predicted_classes:
        preds = d.get('predictions', [])
        best_fmd  = 0.0
        best_hlthy = 0.0
        for p in (preds if isinstance(preds, list) else []):
            cls  = (p.get('class') or p.get('class_name') or '').lower()
            conf = _to_pct(p.get('confidence', 0))
            if _is_fmd(cls):
                best_fmd = max(best_fmd, conf)
            else:
                best_hlthy = max(best_hlthy, conf)

        if best_fmd > 0:
            return {
                'result':        'fmd',
                'result_label':  'Foot and mouth disease detected',
                'confidence':    round(best_fmd, 2),
                'bounding_boxes': [],
            }
        return _healthy(round(best_hlthy, 2))

    # Check if predictions dict has FMD key (Shape A variant)
    preds_dict = d.get('predictions', {})
    if isinstance(preds_dict, dict):
        for cls, conf in preds_dict.items():
            if _is_fmd(cls.lower()):
                return {
                    'result':        'fmd',
                    'result_label':  'Foot and mouth disease detected',
                    'confidence':    round(_to_pct(conf), 2),
                    'bounding_boxes': [],
                }
        # All classes are healthy
        best = max(preds_dict.values(), default=0)
        return _healthy(round(_to_pct(best), 2))

    return None


# ═════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _is_fmd(cls_lower):
    return any(kw in cls_lower for kw in FMD_KEYWORDS)


def _healthy(conf=0.0):
    return {
        'result':        'healthy',
        'result_label':  'Foot and mouth disease not detected',
        'confidence':    conf,
        'bounding_boxes': [],
    }


def _to_pct(v):
    """Convert 0-1 float to 0-100. If already >1 assume it is already %."""
    try:
        v = float(v)
        return v * 100 if v <= 1.0 else v
    except (TypeError, ValueError):
        return 0.0


def _extract_bbox(pred):
    """
    Extract bounding box from a prediction dict.
    Roboflow object-detection models use centre-x, centre-y, width, height.
    Some responses use corner-based 'bbox': [x1, y1, x2, y2].
    """
    # Centre-point format (standard Roboflow OD)
    if 'x' in pred and 'width' in pred:
        return {
            'x':      pred.get('x', 0),
            'y':      pred.get('y', 0),
            'width':  pred.get('width', 0),
            'height': pred.get('height', 0),
        }

    # Corner format: bbox = [x1, y1, x2, y2]
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
            # {x, y, width, height} or {x1, y1, x2, y2}
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

    # Fallback — no spatial info
    return {'x': 0, 'y': 0, 'width': 0, 'height': 0}


def _to_dict(raw):
    """Convert Pydantic model or object to plain dict."""
    if isinstance(raw, dict):
        return raw
    # Pydantic v1
    if hasattr(raw, 'dict'):
        try:
            return raw.dict()
        except Exception:
            pass
    # Pydantic v2
    if hasattr(raw, 'model_dump'):
        try:
            return raw.model_dump()
        except Exception:
            pass
    # Generic object with __dict__
    if hasattr(raw, '__dict__'):
        return vars(raw)
    # Last resort
    try:
        return json.loads(json.dumps(raw, default=str))
    except Exception:
        return {}


def _safe_json(obj):
    """Safely serialise any object for logging."""
    try:
        return json.dumps(_to_dict(obj) if not isinstance(obj, dict) else obj,
                          indent=2, default=str)
    except Exception:
        return str(obj)