"""
recommendations.py
==================
Generates a Recommendation object for every completed Detection.
Called from views.py after analysis is saved.
"""

from .models import Recommendation


def _get_urgency(result, confidence):
    if result == 'fmd':
        if confidence >= 80:
            return 'critical'
        elif confidence >= 60:
            return 'high'
        else:
            return 'moderate'
    return 'low'


def _build_fmd_critical(confidence):
    summary = (
        f"⚠️ CRITICAL: FMD confirmed at {confidence:.1f}% confidence. "
        "Immediate isolation and veterinary intervention required."
    )
    full_text = f"""CRITICAL ALERT — Foot and Mouth Disease Detected ({confidence:.1f}% Confidence)

This level of confidence strongly indicates an active FMD infection. Every minute of delay risks spreading the disease to your entire herd and neighbouring farms.

IMMEDIATE ACTIONS (Do Now — Within the Hour):
1. Isolate the affected animal immediately. Move it to a separate pen away from all other livestock.
2. Stop all animal movement on and off the farm. Do not sell, transport, or relocate any animal.
3. Restrict farm access. Only essential personnel should enter. Provide disinfectant footbaths at all entry points.
4. Contact your veterinary doctor through this system right now to arrange an emergency visit.
5. Do not share equipment, feed troughs, or water sources between the isolated animal and the rest of the herd.

WITHIN 24 HOURS:
6. Notify the District Veterinary Officer (DVO) of Ibanda District as required by Ugandan livestock law.
7. Collect a sample (blister fluid or epithelial tissue) for laboratory confirmation if instructed by your vet.
8. Begin monitoring all other animals in the herd for early symptoms: blisters on hooves, mouth sores, excessive salivation, lameness, or reduced milk production.
9. Record the animal ID, location in the pen, and any visible symptoms for the vet's assessment.

ONGOING:
10. Do not administer any medication without veterinary guidance.
11. Disinfect all areas the animal has occupied using recommended FMD disinfectants (sodium hydroxide 2%, or citric acid 0.2%).
12. Maintain an isolation period of at least 14 days after the last clinical sign disappears.
13. Update vaccination status for the entire herd in consultation with your vet.

FMD is a highly contagious viral disease. Swift action protects your livelihood and your community's livestock."""
    return summary, full_text


def _build_fmd_high(confidence):
    summary = (
        f"⚠️ HIGH ALERT: FMD likely at {confidence:.1f}% confidence. "
        "Isolate animal and contact your vet within 24 hours."
    )
    full_text = f"""HIGH ALERT — Foot and Mouth Disease Likely Detected ({confidence:.1f}% Confidence)

The analysis indicates a likely FMD infection. While laboratory confirmation is recommended, do not wait for results before taking precautions.

RECOMMENDED ACTIONS:
1. Isolate the suspected animal from the rest of the herd as a precaution.
2. Halt all unnecessary animal movement on the farm.
3. Implement basic biosecurity: disinfectant footbaths, restrict visitor access.
4. Contact your veterinary doctor within 24 hours to arrange an examination.
5. Monitor the animal closely for worsening symptoms: blisters, lameness, drooling, or refusal to eat.
6. Check all other animals for similar early signs — pale gums, slight lameness, or tongue blisters.

REPORTING:
7. Inform the District Veterinary Officer if clinical signs are confirmed by your vet.
8. Update vaccination records and check if any animals are due for FMD booster shots.

Early intervention significantly reduces the risk of a full herd outbreak."""
    return summary, full_text


def _build_fmd_moderate(confidence):
    summary = (
        f"⚠️ POSSIBLE FMD: Detection at {confidence:.1f}% confidence. "
        "Monitor closely and consult your vet."
    )
    full_text = f"""MODERATE CONCERN — Possible FMD Indicators Detected ({confidence:.1f}% Confidence)

The system has detected possible indicators of FMD at a moderate confidence level. This may be an early infection or image quality may have affected the result. A physical examination is strongly recommended.

RECOMMENDED ACTIONS:
1. Do not panic, but do not ignore this result. Observe the animal closely.
2. Look for early physical signs: slight lameness, reluctance to eat, mild drooling, or any blistering on the feet or mouth.
3. Separate the animal from the main herd as a precaution if any physical symptoms are visible.
4. Upload a clearer, closer image of the animal's hooves and mouth for a more accurate re-analysis.
5. Contact your veterinary doctor to discuss this result and schedule an inspection at your earliest convenience.
6. Ensure the animal has clean water and adequate nutrition and is not under additional stress.

MONITORING:
7. Check the animal twice daily for any changes in behaviour, appetite, or physical condition.
8. Record any new symptoms with dates in case you need to report to the vet."""
    return summary, full_text


def _build_healthy(confidence):
    summary = f"✅ No FMD detected ({confidence:.1f}% confidence). Continue routine farm management."
    full_text = f"""HEALTHY — No Foot and Mouth Disease Detected ({confidence:.1f}% Confidence)

The AI scan found no indicators of Foot and Mouth Disease in this image. This is a positive result.

CONTINUE GOOD PRACTICE:
1. Maintain regular FMD vaccination schedules for all cattle on the farm.
2. Keep vaccination records up to date in the Vaccination History section of this system.
3. Continue daily observation of your herd for any unusual behaviour or physical changes.
4. Practise good farm biosecurity: disinfect vehicles and equipment entering the farm.
5. Avoid purchasing animals from unknown sources without valid health certificates.
6. Schedule routine vet check-ups at least twice per year.

EARLY WARNING SIGNS TO WATCH FOR:
- Sudden lameness in one or more animals
- Blisters or sores on hooves, tongue, or lips
- Excessive drooling or difficulty eating
- Sudden drop in milk production
- High fever (above 40°C / 104°F)

If any of these signs appear, upload a new image immediately for re-analysis."""
    return summary, full_text


def generate_recommendation(detection):
    """
    Create and save a Recommendation for the given Detection.
    Returns the Recommendation instance.
    """
    # Delete any existing recommendation for this detection
    Recommendation.objects.filter(detection=detection).delete()

    result     = detection.result
    confidence = detection.confidence_score or 0.0

    if result == 'fmd':
        if confidence >= 80:
            summary, full_text = _build_fmd_critical(confidence)
            urgency = 'critical'
        elif confidence >= 60:
            summary, full_text = _build_fmd_high(confidence)
            urgency = 'high'
        else:
            summary, full_text = _build_fmd_moderate(confidence)
            urgency = 'moderate'
    else:
        summary, full_text = _build_healthy(confidence)
        urgency = 'low'

    rec = Recommendation.objects.create(
        detection=detection,
        urgency=urgency,
        summary=summary,
        full_text=full_text,
    )
    return rec
