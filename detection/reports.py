"""
Report generation service for FMD Detection System
Includes: ReportGenerator (farmer), AdminReportGenerator, VetReportGenerator
"""
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
import logging

from .models import Detection, UserProfile

logger = logging.getLogger(__name__)


class BaseReportGenerator:
    def __init__(self):
        self.buffer = BytesIO()
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        self.styles.add(ParagraphStyle(
            name='ReportTitle', parent=self.styles['Heading1'],
            fontSize=22, textColor=colors.HexColor('#1E3A8A'),
            spaceAfter=20, alignment=TA_CENTER, fontName='Helvetica-Bold'
        ))
        self.styles.add(ParagraphStyle(
            name='ReportSubtitle', parent=self.styles['Normal'],
            fontSize=12, textColor=colors.HexColor('#FB923C'),
            spaceAfter=6, alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            name='SectionHeading', parent=self.styles['Heading2'],
            fontSize=14, textColor=colors.HexColor('#1E3A8A'),
            spaceAfter=10, fontName='Helvetica-Bold'
        ))
        self.styles.add(ParagraphStyle(
            name='BodyText2', parent=self.styles['Normal'],
            fontSize=10, spaceAfter=8,
        ))

    def _build_summary_table(self, data):
        summary_data = [
            ['Metric', 'Count', 'Percentage'],
            ['Total Scans', str(data['total_scans']), '100%'],
            ['FMD Detected', str(data['fmd_detected']), f"{data['fmd_percentage']:.1f}%"],
            ['Healthy Cattle', str(data['healthy_cattle']), f"{data['healthy_percentage']:.1f}%"],
            ['Not a Cow', str(data['not_cow']),
             f"{(data['not_cow'] / data['total_scans'] * 100) if data['total_scans'] > 0 else 0:.1f}%"],
            ['Average Confidence', f"{data['avg_confidence']:.1f}%", '-'],
        ]
        t = Table(summary_data, colWidths=[3 * inch, 1.5 * inch, 1.5 * inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F4FF')]),
        ]))
        return t

    def _build_detection_table(self, detections, include_user=False):
        if include_user:
            headers = ['Date', 'User', 'Animal ID', 'Result', 'Confidence', 'Status']
            col_widths = [1.5 * inch, 1.2 * inch, 1 * inch, 1 * inch, 1 * inch, 0.9 * inch]
        else:
            headers = ['Date', 'Animal ID', 'Result', 'Confidence', 'Status']
            col_widths = [1.8 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch, 1.1 * inch]

        rows = [headers]
        for d in detections:
            row = [d.uploaded_at.strftime('%Y-%m-%d %H:%M')]
            if include_user:
                row.append(d.user.get_full_name() or d.user.username)
            row += [
                d.animal_id or 'N/A',
                d.get_result_display() if d.result else 'Pending',
                f"{d.confidence_score:.1f}%" if d.confidence_score else 'N/A',
                d.get_status_display(),
            ]
            rows.append(row)

        t = Table(rows, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FB923C')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FFF8F0')]),
        ]))
        return t

    def _get_date_range_for_type(self, report_type):
        now = timezone.now()
        if report_type == 'daily':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            title = f"Daily Report - {now.strftime('%B %d, %Y')}"
        elif report_type == 'weekly':
            start = now - timedelta(days=7)
            title = f"Weekly Report - {start.strftime('%b %d')} to {now.strftime('%b %d, %Y')}"
        elif report_type == 'monthly':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            title = f"Monthly Report - {now.strftime('%B %Y')}"
        else:
            start = now - timedelta(days=365 * 10)
            title = "All-Time Report"
        return start, now, title

    def _calc_stats(self, detections):
        total = detections.count()
        fmd = detections.filter(result='fmd').count()
        healthy = detections.filter(result='healthy').count()
        not_cow = detections.filter(result='not_cow').count()
        completed = detections.filter(status='completed', confidence_score__isnull=False)
        avg_conf = sum(d.confidence_score for d in completed) / completed.count() if completed.exists() else 0
        return {
            'detections': detections,
            'total_scans': total,
            'fmd_detected': fmd,
            'healthy_cattle': healthy,
            'not_cow': not_cow,
            'avg_confidence': avg_conf,
            'fmd_percentage': (fmd / total * 100) if total > 0 else 0,
            'healthy_percentage': (healthy / total * 100) if total > 0 else 0,
        }

    def _footer_text(self):
        return Paragraph(
            '<i>Generated by FMD Early Detection System · Simba Farms, Ibanda District · support@simbafarmsdetection.com</i>',
            self.styles['BodyText2']
        )


class ReportGenerator(BaseReportGenerator):
    """Farmer report generator"""

    def __init__(self, user, report_type='daily'):
        super().__init__()
        self.user = user
        self.report_type = report_type

    def get_date_range(self):
        return self._get_date_range_for_type(self.report_type)

    def get_report_data(self, start_date, end_date):
        detections = Detection.objects.filter(
            user=self.user, uploaded_at__range=[start_date, end_date]
        ).order_by('-uploaded_at')
        return self._calc_stats(detections)

    def generate(self):
        doc = SimpleDocTemplate(self.buffer, pagesize=A4,
                                rightMargin=60, leftMargin=60, topMargin=60, bottomMargin=40)
        elements = []
        start_date, end_date, title = self.get_date_range()
        data = self.get_report_data(start_date, end_date)

        elements.append(Paragraph("FMD Early Detection System", self.styles['ReportTitle']))
        elements.append(Paragraph("Simba Farms, Ibanda District", self.styles['ReportSubtitle']))
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(title, self.styles['SectionHeading']))
        elements.append(Paragraph(
            f"<b>Generated For:</b> {self.user.get_full_name() or self.user.email} &nbsp;|&nbsp; "
            f"<b>Generated On:</b> {timezone.now().strftime('%B %d, %Y at %I:%M %p')}",
            self.styles['BodyText2']
        ))
        elements.append(Spacer(1, 15))
        elements.append(Paragraph("Summary Statistics", self.styles['SectionHeading']))
        elements.append(self._build_summary_table(data))
        elements.append(Spacer(1, 15))

        if data['fmd_detected'] > 0:
            elements.append(Paragraph("⚠️ ALERT: FMD Cases Detected", self.styles['SectionHeading']))
            elements.append(Paragraph(
                f"<font color='red'><b>{data['fmd_detected']} FMD case(s) detected. Isolate animals and contact a veterinary officer immediately.</b></font>",
                self.styles['BodyText2']
            ))
            elements.append(Spacer(1, 10))

        if data['detections'].exists():
            elements.append(Paragraph("Detection Records", self.styles['SectionHeading']))
            elements.append(self._build_detection_table(data['detections']))
        else:
            elements.append(Paragraph("No detection records for this period.", self.styles['BodyText2']))

        elements.append(Spacer(1, 20))
        elements.append(self._footer_text())
        doc.build(elements)
        pdf = self.buffer.getvalue()
        self.buffer.close()
        return pdf


class AdminReportGenerator(BaseReportGenerator):
    """System-wide report for admin"""

    def __init__(self, report_type='daily'):
        super().__init__()
        self.report_type = report_type

    def generate(self):
        doc = SimpleDocTemplate(self.buffer, pagesize=A4,
                                rightMargin=60, leftMargin=60, topMargin=60, bottomMargin=40)
        elements = []
        start_date, end_date, title = self._get_date_range_for_type(self.report_type)

        detections = Detection.objects.filter(
            uploaded_at__range=[start_date, end_date]
        ).select_related('user').order_by('-uploaded_at')
        data = self._calc_stats(detections)

        elements.append(Paragraph("FMD Early Detection System — Admin Report", self.styles['ReportTitle']))
        elements.append(Paragraph("Simba Farms, Ibanda District", self.styles['ReportSubtitle']))
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(title, self.styles['SectionHeading']))
        elements.append(Paragraph(
            f"<b>Generated On:</b> {timezone.now().strftime('%B %d, %Y at %I:%M %p')} &nbsp;|&nbsp; <b>Scope:</b> All Users",
            self.styles['BodyText2']
        ))
        elements.append(Spacer(1, 15))

        # User summary
        from django.contrib.auth.models import User
        total_farmers = User.objects.filter(profile__role='farmer').count()
        total_vets = User.objects.filter(profile__role='vet').count()
        elements.append(Paragraph("System Overview", self.styles['SectionHeading']))
        overview_data = [
            ['Registered Farmers', str(total_farmers)],
            ['Registered Vets', str(total_vets)],
        ]
        ov_table = Table(overview_data, colWidths=[3 * inch, 2 * inch])
        ov_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#EEF2FF'), colors.white]),
        ]))
        elements.append(ov_table)
        elements.append(Spacer(1, 15))

        elements.append(Paragraph("Detection Summary", self.styles['SectionHeading']))
        elements.append(self._build_summary_table(data))
        elements.append(Spacer(1, 15))

        if data['fmd_detected'] > 0:
            elements.append(Paragraph("⚠️ FMD Alerts", self.styles['SectionHeading']))
            elements.append(Paragraph(
                f"<font color='red'><b>{data['fmd_detected']} FMD case(s) detected system-wide. Immediate veterinary review required.</b></font>",
                self.styles['BodyText2']
            ))
            elements.append(Spacer(1, 10))

        if data['detections'].exists():
            elements.append(Paragraph("All Detection Records", self.styles['SectionHeading']))
            elements.append(self._build_detection_table(data['detections'], include_user=True))
        else:
            elements.append(Paragraph("No detections recorded for this period.", self.styles['BodyText2']))

        elements.append(Spacer(1, 20))
        elements.append(self._footer_text())
        doc.build(elements)
        pdf = self.buffer.getvalue()
        self.buffer.close()
        return pdf


class VetReportGenerator(BaseReportGenerator):
    """Vet report: includes both vet's own detections and all farm detections"""

    def __init__(self, vet_user, report_type='daily'):
        super().__init__()
        self.vet_user = vet_user
        self.report_type = report_type

    def get_date_range(self):
        return self._get_date_range_for_type(self.report_type)

    def get_report_data(self, start_date, end_date):
        detections = Detection.objects.filter(
            uploaded_at__range=[start_date, end_date]
        ).select_related('user').order_by('-uploaded_at')
        return self._calc_stats(detections)

    def generate(self):
        doc = SimpleDocTemplate(self.buffer, pagesize=A4,
                                rightMargin=60, leftMargin=60, topMargin=60, bottomMargin=40)
        elements = []
        start_date, end_date, title = self.get_date_range()
        data = self.get_report_data(start_date, end_date)

        # Vet's own detections
        vet_detections = Detection.objects.filter(
            user=self.vet_user, uploaded_at__range=[start_date, end_date]
        ).order_by('-uploaded_at')
        vet_data = self._calc_stats(vet_detections)

        elements.append(Paragraph("FMD Early Detection System — Veterinary Report", self.styles['ReportTitle']))
        elements.append(Paragraph("Simba Farms, Ibanda District", self.styles['ReportSubtitle']))
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(title, self.styles['SectionHeading']))
        elements.append(Paragraph(
            f"<b>Veterinarian:</b> Dr. {self.vet_user.get_full_name()} &nbsp;|&nbsp; "
            f"<b>Generated:</b> {timezone.now().strftime('%B %d, %Y at %I:%M %p')}",
            self.styles['BodyText2']
        ))
        elements.append(Spacer(1, 15))

        elements.append(Paragraph("Farm-Wide Summary (All Uploads)", self.styles['SectionHeading']))
        elements.append(self._build_summary_table(data))
        elements.append(Spacer(1, 15))

        elements.append(Paragraph("My Detections Summary", self.styles['SectionHeading']))
        elements.append(self._build_summary_table(vet_data))
        elements.append(Spacer(1, 15))

        if data['fmd_detected'] > 0:
            elements.append(Paragraph("⚠️ FMD Alerts — Farm-Wide", self.styles['SectionHeading']))
            elements.append(Paragraph(
                f"<font color='red'><b>{data['fmd_detected']} FMD case(s) detected on the farm. Immediate action required.</b></font>",
                self.styles['BodyText2']
            ))
            elements.append(Spacer(1, 10))

        if data['detections'].exists():
            elements.append(Paragraph("All Farm Detection Records", self.styles['SectionHeading']))
            elements.append(self._build_detection_table(data['detections'], include_user=True))
        else:
            elements.append(Paragraph("No detections for this period.", self.styles['BodyText2']))

        elements.append(Spacer(1, 20))
        elements.append(self._footer_text())
        doc.build(elements)
        pdf = self.buffer.getvalue()
        self.buffer.close()
        return pdf
