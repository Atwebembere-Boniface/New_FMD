"""
Service module for FMD detection using Roboflow API
"""
from inference_sdk import InferenceHTTPClient
from django.conf import settings
import os
import logging

logger = logging.getLogger(__name__)

# Get API credentials from environment variables
ROBOFLOW_API_KEY = os.environ.get('ROBOFLOW_API_KEY', 'rhxZDhXeLQ78qGGsVT9H')
MODEL_ID = os.environ.get('ROBOFLOW_MODEL_ID', 'cows-mien3/1')

# Initialize Roboflow client
CLIENT = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=ROBOFLOW_API_KEY
)


def analyze_cattle_image(image_path):
    """
    Analyze cattle image using Roboflow model
    
    Args:
        image_path: Path to the cattle image file
        
    Returns:
        dict: Analysis results with status, result, and confidence
    """
    try:
        # Call Roboflow API
        result = CLIENT.infer(image_path, model_id=MODEL_ID)
        
        # Log the raw result for debugging
        logger.info(f"Roboflow API Response: {result}")
        
        # Parse the result
        analysis = parse_roboflow_result(result)
        
        return {
            'success': True,
            'status': 'completed',  # Changed from 'completed' to ensure it's always completed
            'result': analysis['result'],
            'confidence_score': analysis['confidence'],
            'raw_data': result
        }
        
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return {
            'success': False,
            'status': 'failed',
            'result': 'inconclusive',
            'confidence_score': 0.0,
            'error': str(e)
        }


def parse_roboflow_result(result):
    """
    Parse Roboflow API response to extract detection results
    
    Args:
        result: Raw response from Roboflow API
        
    Returns:
        dict: Parsed result with 'result' and 'confidence'
    """
    try:
        # Check if predictions exist
        if 'predictions' not in result or not result['predictions']:
            return {
                'result': 'not_cow',
                'confidence': 0.0
            }
        
        # Get the highest confidence prediction
        predictions = result['predictions']
        highest_confidence_pred = max(predictions, key=lambda x: x.get('confidence', 0))
        
        # Extract class and confidence
        detected_class = highest_confidence_pred.get('class', '').lower()
        confidence = highest_confidence_pred.get('confidence', 0.0) * 100  # Convert to percentage
        
        # Map detected class to our result categories
        if 'fmd' in detected_class or 'foot-and-mouth' in detected_class or 'disease' in detected_class:
            result_category = 'fmd'
        elif 'healthy' in detected_class or 'normal' in detected_class:
            result_category = 'healthy'
        elif 'cow' in detected_class or 'cattle' in detected_class:
            # If it's just labeled as cow without health status, mark as inconclusive
            result_category = 'inconclusive'
        else:
            result_category = 'not_cow'
        
        return {
            'result': result_category,
            'confidence': round(confidence, 2)
        }
        
    except Exception as e:
        logger.error(f"Error parsing Roboflow result: {str(e)}")
        return {
            'result': 'inconclusive',
            'confidence': 0.0
        }


def get_detection_summary(predictions):
    """
    Get a summary of all detections in the image
    
    Args:
        predictions: List of predictions from Roboflow
        
    Returns:
        dict: Summary with counts and details
    """
    summary = {
        'total_cows': 0,
        'healthy_count': 0,
        'fmd_count': 0,
        'detections': []
    }
    
    for pred in predictions:
        detected_class = pred.get('class', '').lower()
        confidence = pred.get('confidence', 0.0) * 100
        
        detection_info = {
            'class': detected_class,
            'confidence': round(confidence, 2),
            'bbox': {
                'x': pred.get('x', 0),
                'y': pred.get('y', 0),
                'width': pred.get('width', 0),
                'height': pred.get('height', 0)
            }
        }
        
        summary['detections'].append(detection_info)
        
        # Count by category
        if 'fmd' in detected_class or 'disease' in detected_class:
            summary['fmd_count'] += 1
            summary['total_cows'] += 1
        elif 'healthy' in detected_class:
            summary['healthy_count'] += 1
            summary['total_cows'] += 1
        elif 'cow' in detected_class or 'cattle' in detected_class:
            summary['total_cows'] += 1
    
    return summary