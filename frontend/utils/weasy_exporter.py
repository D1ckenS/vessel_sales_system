import io
import base64
from datetime import datetime
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.conf import settings
import weasyprint
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import logging
import matplotlib.pyplot as plt

plt.style.use('default')  # <— ✅ One-time global style setting

# Set up logging
logger = logging.getLogger(__name__)

class WeasyPrintExporter:
    def __init__(self, title="Report", template_type="standard", orientation="portrait", 
                 language="en", rtl_labels=None):
        """
        Initialize WeasyPrint exporter with RTL support
        
        Args:
            title: Report title
            template_type: 'standard', 'wide', 'analytics'
            orientation: 'portrait' or 'landscape'
            language: 'en' or 'ar' for RTL support
            rtl_labels: Dictionary with translated labels for RTL
        """
        self.title = title
        self.template_type = template_type
        self.orientation = orientation
        self.language = language
        self.rtl_labels = rtl_labels or {}
        self.metadata = {}
        self.tables = []
        self.charts = []
        self.summary_data = {}
        
    def add_metadata(self, metadata):
        """Add metadata to the report"""
        self.metadata = metadata or {}
        
    def add_table(self, headers, data, table_title=None, table_id=None):
        """Add a table to the report"""
        if not data and not headers:
            return
            
        table_data = {
            'title': table_title,
            'id': table_id or f'table_{len(self.tables)}',
            'headers': headers or [],
            'rows': []
        }
        
        # Process data rows
        for row in (data or []):
            if row:
                processed_row = []
                for cell in row:
                    if cell is None:
                        processed_row.append('')
                    else:
                        processed_row.append(str(cell))
                table_data['rows'].append(processed_row)
        
        self.tables.append(table_data)
        
    def add_summary(self, summary_data):
        """Add summary data to the report"""
        self.summary_data = summary_data or {}
        
    def add_chart(self, chart_data, chart_type='bar', chart_title='Chart', chart_id=None):
        """
        Add a chart to the report
        
        Args:
            chart_data: List of tuples [(label, value), ...]
            chart_type: 'bar', 'pie', 'line'
            chart_title: Chart title
            chart_id: Unique chart identifier
        """
        try:
            if not chart_data:
                return
                
            labels, values = zip(*chart_data)
            # Create matplotlib figure
            fig, ax = plt.subplots(figsize=(8, 4))
            
            if chart_type == 'bar':
                bars = ax.bar(labels, values, color='#2c3e50', alpha=0.8)
                ax.set_ylabel('Value')
                
                # Add value labels on bars
                for bar, value in zip(bars, values):
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width() / 2., height, format(float(value), '.2f'), ha='center', va='bottom')
                           
            elif chart_type == 'pie':
                ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
                
            elif chart_type == 'line':
                ax.plot(labels, values, marker='o', linewidth=2, markersize=6)
                ax.set_ylabel('Value')
                
            ax.set_title(chart_title, fontsize=14, fontweight='bold', pad=20)
            ax.grid(True, alpha=0.3)
            
            # Rotate x-axis labels if needed
            if len(str(labels[0]) if labels else '') > 8:
                plt.xticks(rotation=45, ha='right')
                
            plt.tight_layout()
            try:
                # Convert to base64 string
                buffer = io.BytesIO()
                plt.savefig(buffer, format='png', dpi=120, bbox_inches='tight', 
                        facecolor='white', edgecolor='none')
                buffer.seek(0)
                
                chart_base64 = base64.b64encode(buffer.getvalue()).decode()
            finally:
                plt.close(fig)
            
            self.charts.append({
                'id': chart_id or f'chart_{len(self.charts)}',
                'title': chart_title,
                'data': chart_base64,
                'type': chart_type
            })
            
        except Exception as e:
            logger.error(f"Error creating chart: {e}")
            # Don't fail the whole report, just skip the chart
            pass
           
    def get_response(self, filename):
        """Generate HTTP response with PDF file - Enhanced with RTL support"""
        try:
            # Select template based on type and orientation
            if self.template_type == 'analytics':
                template_name = 'frontend/exports/analytics_export.html'
            elif self.orientation == 'landscape' or self.template_type == 'wide':
                template_name = 'frontend/exports/wide_report.html'
            else:
                template_name = 'frontend/exports/standard_report.html'
                
            # Enhanced context with RTL support
            context = {
                'title': self.title,
                'metadata': self.metadata,
                'tables': self.tables,
                'charts': self.charts,
                'summary_data': self.summary_data,
                'orientation': self.orientation,
                'generation_date': self._format_generation_date(),
                'has_logo': False,  # Will be True when logo is added
                
                # RTL support variables (with fallback defaults)
                'language': self.language,
                'generated_on_text': self.rtl_labels.get('generated_on', 'Generated on'),
                'report_info_text': self.rtl_labels.get('report_information', 'Report Information'),
                'summary_text': self.rtl_labels.get('summary', 'Summary'),
                'company_logo_text': self.rtl_labels.get('company_logo', 'COMPANY LOGO'),
                'no_data_text': self.rtl_labels.get('no_data_available', 'No data available'),
            }
            
            # Render HTML
            html_string = render_to_string(template_name, context)
            
            # Create PDF
            html = weasyprint.HTML(string=html_string)
            css_string = self._get_css_styles()
            css = weasyprint.CSS(string=css_string)
            
            # Generate PDF
            buffer = io.BytesIO()
            html.write_pdf(target=buffer, stylesheets=[css])
            buffer.seek(0)
            
            # Clean filename
            clean_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.'))
            if not clean_filename.endswith('.pdf'):
                clean_filename += '.pdf'
            
            # Create response
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{clean_filename}"'
            response['Content-Length'] = len(buffer.getvalue())
            response.write(buffer.getvalue())
            
            return response
            
        except Exception as e:
            logger.error(f"WeasyPrint PDF generation error: {e}")
            raise Exception(f"PDF generation failed: {str(e)}")
    
    def _format_generation_date(self):
        """Format generation date based on language"""
        if self.language == 'ar':
            # You can implement Arabic date formatting here if needed
            return datetime.now().strftime('%d/%m/%Y %H:%M')
        else:
            return datetime.now().strftime('%d/%m/%Y %H:%M')
    
    def _get_css_styles(self):
        """Get CSS styles for the report"""
        return """
        @page {
            size: A4;
            margin: 0.75in;
        }
        
        body {
            font-family: Arial, sans-serif;
            font-size: 12px;
            line-height: 1.4;
            color: #333;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 2px solid #2c3e50;
            padding-bottom: 20px;
        }
        
        .title {
            font-size: 20px;
            font-weight: bold;
            color: #2c3e50;
            margin: 10px 0;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            font-size: 10px;
        }
        
        th, td {
            border: 1px solid #ddd;
            padding: 4px;
            text-align: left;
        }
        
        th {
            background-color: #2c3e50;
            color: white;
            font-weight: bold;
        }
        
        .metadata, .summary {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 25px;
        }
        
        .no-break {
            page-break-inside: avoid;
        }
        
        .chart-container {
            margin: 25px 0;
            text-align: center;
            page-break-inside: avoid;
        }
        
        .chart-title {
            font-size: 16px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 15px;
        }
        
        .chart-image {
            max-width: 100%;
            height: auto;
            border: 1px solid #dee2e6;
            border-radius: 5px;
        }
        
        .page-break {
            page-break-before: always;
        }
        
        .no-break {
            page-break-inside: avoid;
        }
        
        @media print {
            .no-print {
                display: none;
            }
        }
        """

def create_weasy_exporter(title, template_type="standard", orientation="portrait", 
                         language="en", rtl_labels=None):
    """
    Helper function to create WeasyPrint exporter with RTL support
    
    Args:
        title: Report title
        template_type: 'standard', 'wide', 'analytics'
        orientation: 'portrait' or 'landscape'
        language: 'en' or 'ar' for RTL support
        rtl_labels: Dictionary with translated labels
    """
    try:
        return WeasyPrintExporter(
            title=title, 
            template_type=template_type, 
            orientation=orientation,
            language=language,
            rtl_labels=rtl_labels
        )
    except Exception as e:
        logger.error(f"Error creating WeasyPrint exporter: {e}")
        raise Exception(f"Failed to create WeasyPrint exporter: {str(e)}")


def create_weasy_exporter_for_data(title, data_width="normal", language="en", rtl_labels=None):
    """
    Helper function to create appropriately configured WeasyPrint exporter with RTL support
    
    Args:
        title: Report title
        data_width: "normal" for portrait, "wide" for landscape
        language: 'en' or 'ar' for RTL support
        rtl_labels: Dictionary with translated labels
    """
    try:
        if data_width == "wide":
            return WeasyPrintExporter(
                title=title, 
                template_type="wide", 
                orientation="landscape",
                language=language,
                rtl_labels=rtl_labels
            )
        else:
            return WeasyPrintExporter(
                title=title, 
                template_type="standard", 
                orientation="portrait",
                language=language,
                rtl_labels=rtl_labels
            )
    except Exception as e:
        logger.error(f"Error creating WeasyPrint exporter: {e}")
        raise Exception(f"Failed to create WeasyPrint exporter: {str(e)}")
