"""
Report generation service for FMD Detection System
"""
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta, datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.platypus import Image as RLImage
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO
import logging

from .models import Detection, UserProfile

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generate PDF reports for FMD detections"""
    
    def __init__(self, user, report_type='daily'):
        self.user = user
        self.report_type = report_type
        self.buffer = BytesIO()
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
        
    def setup_custom_styles(self):
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2196F3'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#1565C0'),
            spaceAfter=12,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomBody',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=12,
        ))
    
    def get_date_range(self):
        """Get date range based on report type"""
        now = timezone.now()
        
        if self.report_type == 'daily':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
            title = f"Daily Report - {now.strftime('%B %d, %Y')}"
        elif self.report_type == 'weekly':
            start_date = now - timedelta(days=7)
            end_date = now
            title = f"Weekly Report - {start_date.strftime('%b %d')} to {end_date.strftime('%b %d, %Y')}"
        elif self.report_type == 'monthly':
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = now
            title = f"Monthly Report - {now.strftime('%B %Y')}"
        else:
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
            title = "Report"
        
        return start_date, end_date, title
    
    def get_report_data(self, start_date, end_date):
        """Fetch detection data for the date range"""
        detections = Detection.objects.filter(
            user=self.user,
            uploaded_at__range=[start_date, end_date]
        ).order_by('-uploaded_at')
        
        # Calculate statistics
        total_scans = detections.count()
        fmd_detected = detections.filter(result='fmd').count()
        healthy_cattle = detections.filter(result='healthy').count()
        not_cow = detections.filter(result='not_cow').count()
        inconclusive = detections.filter(result='inconclusive').count()
        
        # Calculate average confidence
        completed = detections.filter(status='completed', confidence_score__isnull=False)
        avg_confidence = 0
        if completed.exists():
            avg_confidence = sum(d.confidence_score for d in completed) / completed.count()
        
        return {
            'detections': detections,
            'total_scans': total_scans,
            'fmd_detected': fmd_detected,
            'healthy_cattle': healthy_cattle,
            'not_cow': not_cow,
            'inconclusive': inconclusive,
            'avg_confidence': avg_confidence,
            'fmd_percentage': (fmd_detected / total_scans * 100) if total_scans > 0 else 0,
            'healthy_percentage': (healthy_cattle / total_scans * 100) if total_scans > 0 else 0,
        }
    
    def generate(self):
        """Generate the complete PDF report"""
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )
        
        # Container for the 'Flowable' objects
        elements = []
        
        # Get date range and data
        start_date, end_date, title = self.get_date_range()
        data = self.get_report_data(start_date, end_date)
        
        # Header
        elements.append(Paragraph("FMD Early Detection System", self.styles['CustomTitle']))
        elements.append(Paragraph("Simba Farms, Ibanda District", self.styles['CustomBody']))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(title, self.styles['CustomHeading']))
        elements.append(Spacer(1, 12))
        
        # User Information
        try:
            profile = self.user.profile
            user_info = f"""
            <b>Report Generated For:</b> {self.user.get_full_name()}<br/>
            <b>Farm:</b> {profile.farm_name}<br/>
            <b>Location:</b> {profile.location}<br/>
            <b>Generated On:</b> {timezone.now().strftime('%B %d, %Y at %I:%M %p')}
            """
        except:
            user_info = f"""
            <b>Report Generated For:</b> {self.user.username}<br/>
            <b>Generated On:</b> {timezone.now().strftime('%B %d, %Y at %I:%M %p')}
            """
        
        elements.append(Paragraph(user_info, self.styles['CustomBody']))
        elements.append(Spacer(1, 20))
        
        # Summary Statistics
        elements.append(Paragraph("Summary Statistics", self.styles['CustomHeading']))
        
        summary_data = [
            ['Metric', 'Count', 'Percentage'],
            ['Total Scans', str(data['total_scans']), '100%'],
            ['FMD Detected', str(data['fmd_detected']), f"{data['fmd_percentage']:.1f}%"],
            ['Healthy Cattle', str(data['healthy_cattle']), f"{data['healthy_percentage']:.1f}%"],
            ['Not a Cow', str(data['not_cow']), f"{(data['not_cow']/data['total_scans']*100) if data['total_scans'] > 0 else 0:.1f}%"],
            ['Inconclusive', str(data['inconclusive']), f"{(data['inconclusive']/data['total_scans']*100) if data['total_scans'] > 0 else 0:.1f}%"],
            ['Average Confidence', f"{data['avg_confidence']:.2f}%", '-'],
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ]))
        
        elements.append(summary_table)
        elements.append(Spacer(1, 20))
        
        # Alerts Section
        if data['fmd_detected'] > 0:
            elements.append(Paragraph("⚠️ CRITICAL ALERTS", self.styles['CustomHeading']))
            alert_text = f"""
            <font color="red"><b>{data['fmd_detected']} case(s) of FMD detected during this period!</b></font><br/>
            <b>Immediate Action Required:</b><br/>
            • Isolate affected animals immediately<br/>
            • Contact veterinary officer<br/>
            • Implement biosecurity measures<br/>
            • Monitor other animals closely
            """
            elements.append(Paragraph(alert_text, self.styles['CustomBody']))
            elements.append(Spacer(1, 20))
        
        # Detailed Detection Records
        if data['detections'].exists():
            elements.append(Paragraph("Detailed Detection Records", self.styles['CustomHeading']))
            
            detection_data = [['Date', 'Animal ID', 'Result', 'Confidence', 'Status']]
            
            for detection in data['detections']:
                detection_data.append([
                    detection.uploaded_at.strftime('%Y-%m-%d %H:%M'),
                    detection.animal_id or 'N/A',
                    detection.get_result_display() if detection.result else 'Pending',
                    f"{detection.confidence_score:.1f}%" if detection.confidence_score else 'N/A',
                    detection.get_status_display(),
                ])
            
            detection_table = Table(detection_data, colWidths=[1.8*inch, 1.2*inch, 1.2*inch, 1.2*inch, 1*inch])
            detection_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4CAF50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            
            elements.append(detection_table)
        else:
            elements.append(Paragraph("No detection records found for this period.", self.styles['CustomBody']))
        
        elements.append(Spacer(1, 20))
        
        # Recommendations
        elements.append(Paragraph("Recommendations", self.styles['CustomHeading']))
        
        recommendations = self._generate_recommendations(data)
        elements.append(Paragraph(recommendations, self.styles['CustomBody']))
        
        # Footer
        elements.append(Spacer(1, 30))
        footer_text = """
        <i>This report was automatically generated by the FMD Early Detection System.<br/>
        For questions or support, contact: support@simbafarmsdetection.com</i>
        """
        elements.append(Paragraph(footer_text, self.styles['CustomBody']))
        
        # Build PDF
        doc.build(elements)
        
        # Get the value of the BytesIO buffer and return it
        pdf = self.buffer.getvalue()
        self.buffer.close()
        return pdf
    
    def _generate_recommendations(self, data):
        """Generate recommendations based on detection data"""
        recommendations = []
        
        if data['fmd_detected'] > 0:
            recommendations.append("• <b>URGENT:</b> FMD cases detected. Implement immediate quarantine and contact veterinary services.")
        
        if data['fmd_percentage'] > 10:
            recommendations.append("• High FMD detection rate. Consider mass screening of the entire herd.")
        
        if data['total_scans'] < 5 and self.report_type == 'daily':
            recommendations.append("• Consider increasing monitoring frequency for early detection.")
        
        if data['avg_confidence'] < 70 and data['avg_confidence'] > 0:
            recommendations.append("• Average confidence is below 70%. Ensure images are clear and well-lit for better accuracy.")
        
        if data['healthy_cattle'] == data['total_scans']:
            recommendations.append("• ✓ All scanned cattle appear healthy. Continue regular monitoring and good farm hygiene practices.")
        
        if not recommendations:
            recommendations.append("• Continue regular monitoring and maintain good biosecurity practices.")
            recommendations.append("• Ensure all cattle are regularly checked for symptoms.")
            recommendations.append("• Keep records updated for trend analysis.")
        
        return '<br/>'.join(recommendations)