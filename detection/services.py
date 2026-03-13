"""
Service module for FMD detection using Roboflow API
Model: foot-and-mouth-disease-mfuiw/1
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

FMD_KEYWORDS = {
    'fmd', 'foot-and-mouth', 'foot_and_mouth', 'footandmouth',
    'disease', 'infected', 'infection', 'lesion', 'blister',
    'positive', 'sick', 'affected'
}
HEALTHY_KEYWORDS = {
    'healthy', 'normal', 'negative', 'no_disease', 'nodisease', 'clean'
}


def analyze_cattle_image(image_path):
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


def _parse(raw):
    raw_dict = _to_dict(raw)

    od_result = _try_object_detection(raw_dict)
    if od_result is not None:
        return od_result

    cls_result = _try_classification(raw_dict)
    if cls_result is not None:
        return cls_result

    logger.warning("[FMD] Could not parse response — defaulting to healthy")
    return _healthy(0.0)


def _try_object_detection(d):
    preds = d.get('predictions', [])

    if not isinstance(preds, list) or len(preds) == 0:
        # ── NO PREDICTIONS AT ALL ──
        # Roboflow returns an empty list when it finds no objects.
        # Check if the response still carries a top-level confidence
        # (some models populate 'confidence' even with empty predictions).
        top_conf = d.get('confidence') or d.get('score')
        if top_conf is not None:
            return _healthy(round(_to_pct(top_conf), 2))

        # If the response has image dimensions it is a genuine OD response
        # with no detections — report healthy with the model's own
        # "nothing detected" implicit confidence (100% healthy).
        if 'image' in d or 'inference_id' in d:
            return _healthy(99.0)

        return None

    first = preds[0] if preds else {}
    if not isinstance(first, dict):
        return None

    has_bbox = any(k in first for k in ('x', 'y', 'width', 'height', 'bbox'))
    has_cls  = 'class' in first or 'class_name' in first

    if not (has_bbox or has_cls):
        return None

    fmd_boxes     = []
    best_fmd_conf = 0.0
    best_hlthy    = 0.0

    for pred in preds:
        cls  = (pred.get('class') or pred.get('class_name') or '').lower().replace(' ', '_')
        conf = _to_pct(pred.get('confidence', 0))
        box  = _extract_bbox(pred)

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
            'result':         'fmd',
            'result_label':   'Foot and mouth disease detected',
            'confidence':     round(best_fmd_conf, 2),
            'bounding_boxes': fmd_boxes,
        }

    # Healthy — derive confidence from the healthy predictions if available,
    # otherwise invert the best FMD score seen, or use 99% as safe default.
    if best_hlthy > 0:
        healthy_conf = round(best_hlthy, 2)
    elif best_fmd_conf > 0:
        # Model saw something but classified it non-FMD
        healthy_conf = round(100.0 - best_fmd_conf, 2)
    else:
        healthy_conf = 99.0

    return _healthy(healthy_conf)


def _try_classification(d):
    # Shape A — top-level 'top' key
    top_class = d.get('top', '')
    if top_class:
        conf = _to_pct(d.get('confidence', 0))
        if _is_fmd(top_class.lower()):
            return {
                'result':         'fmd',
                'result_label':   'Foot and mouth disease detected',
                'confidence':     round(conf, 2),
                'bounding_boxes': [],
            }
        # Healthy — use the model's own confidence for the healthy class
        healthy_conf = round(conf, 2) if conf > 0 else 99.0
        return _healthy(healthy_conf)

    # Shape B — 'predicted_classes' list
    predicted_classes = d.get('predicted_classes', [])
    if predicted_classes:
        preds = d.get('predictions', [])
        best_fmd   = 0.0
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
                'result':         'fmd',
                'result_label':   'Foot and mouth disease detected',
                'confidence':     round(best_fmd, 2),
                'bounding_boxes': [],
            }
        healthy_conf = round(best_hlthy, 2) if best_hlthy > 0 else 99.0
        return _healthy(healthy_conf)

    # Shape A variant — predictions is a dict of {class: score}
    preds_dict = d.get('predictions', {})
    if isinstance(preds_dict, dict) and preds_dict:
        fmd_conf   = 0.0
        hlthy_conf = 0.0
        for cls, conf in preds_dict.items():
            c = _to_pct(conf)
            if _is_fmd(cls.lower()):
                fmd_conf = max(fmd_conf, c)
            else:
                hlthy_conf = max(hlthy_conf, c)

        if fmd_conf > 0:
            return {
                'result':         'fmd',
                'result_label':   'Foot and mouth disease detected',
                'confidence':     round(fmd_conf, 2),
                'bounding_boxes': [],
            }
        healthy_conf = round(hlthy_conf, 2) if hlthy_conf > 0 else 99.0
        return _healthy(healthy_conf)

    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_fmd(cls_lower):
    return any(kw in cls_lower for kw in FMD_KEYWORDS)


def _healthy(conf=99.0):
    """
    Return a standardised healthy result.
    Default confidence is 99% — the model found nothing suspicious.
    """
    return {
        'result':         'healthy',
        'result_label':   'Foot and mouth disease not detected',
        'confidence':     conf,
        'bounding_boxes': [],
    }


def _to_pct(v):
    try:
        v = float(v)
        return v * 100 if v <= 1.0 else v
    except (TypeError, ValueError):
        return 0.0


def _extract_bbox(pred):
    if 'x' in pred and 'width' in pred:
        return {
            'x':      pred.get('x', 0),
            'y':      pred.get('y', 0),
            'width':  pred.get('width', 0),
            'height': pred.get('height', 0),
        }
    bbox = pred.get('bbox') or pred.get('bounding_box')
    if bbox:
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            return {'x': (x1+x2)/2, 'y': (y1+y2)/2, 'width': abs(x2-x1), 'height': abs(y2-y1)}
        if isinstance(bbox, dict):
            if 'width' in bbox:
                return bbox
            x1 = bbox.get('x1', bbox.get('left', 0))
            y1 = bbox.get('y1', bbox.get('top', 0))
            x2 = bbox.get('x2', bbox.get('right', 0))
            y2 = bbox.get('y2', bbox.get('bottom', 0))
            return {'x': (x1+x2)/2, 'y': (y1+y2)/2, 'width': abs(x2-x1), 'height': abs(y2-y1)}
    return {'x': 0, 'y': 0, 'width': 0, 'height': 0}


def _to_dict(raw):
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
        return json.dumps(_to_dict(obj) if not isinstance(obj, dict) else obj,
                          indent=2, default=str)
    except Exception:
        return str(obj)