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

# Set up logging
logger = logging.getLogger(__name__)

class WeasyPrintExporter:
    def __init__(self, title="Report", template_type="standard", orientation="portrait"):
        """
        Initialize WeasyPrint exporter
        
        Args:
            title: Report title
            template_type: 'standard', 'wide', 'analytics'
            orientation: 'portrait' or 'landscape'
        """
        self.title = title
        self.template_type = template_type
        self.orientation = orientation
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
                        cell_str = str(cell)
                        # Handle long text for display
                        if len(cell_str) > 80:
                            processed_row.append(cell_str[:77] + '...')
                        else:
                            processed_row.append(cell_str)
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
                
            # Create matplotlib figure
            plt.style.use('default')
            fig, ax = plt.subplots(figsize=(10, 6))
            
            if chart_type == 'bar':
                labels, values = zip(*chart_data)
                bars = ax.bar(labels, values, color='#2c3e50', alpha=0.8)
                ax.set_ylabel('Value')
                
                # Add value labels on bars
                for bar, value in zip(bars, values):
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{value:.2f}', ha='center', va='bottom')
                           
            elif chart_type == 'pie':
                labels, values = zip(*chart_data)
                ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
                
            elif chart_type == 'line':
                labels, values = zip(*chart_data)
                ax.plot(labels, values, marker='o', linewidth=2, markersize=6)
                ax.set_ylabel('Value')
                
            ax.set_title(chart_title, fontsize=14, fontweight='bold', pad=20)
            ax.grid(True, alpha=0.3)
            
            # Rotate x-axis labels if needed
            if len(str(labels[0]) if labels else '') > 8:
                plt.xticks(rotation=45, ha='right')
                
            plt.tight_layout()
            
            # Convert to base64 string
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            buffer.seek(0)
            
            chart_base64 = base64.b64encode(buffer.getvalue()).decode()
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
        """Generate HTTP response with PDF file"""
        try:
            # Select template based on type and orientation
            if self.template_type == 'analytics':
                template_name = 'frontend/exports/analytics_export.html'
            elif self.orientation == 'landscape' or self.template_type == 'wide':
                template_name = 'frontend/exports/wide_report.html'
            else:
                template_name = 'frontend/exports/standard_report.html'
                
            # Prepare context
            context = {
                'title': self.title,
                'metadata': self.metadata,
                'tables': self.tables,
                'charts': self.charts,
                'summary_data': self.summary_data,
                'orientation': self.orientation,
                'generation_date': datetime.now().strftime('%d/%m/%Y %H:%M'),
                'has_logo': False,  # Will be True when logo is added
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
                
            # Create HTTP response
            response = HttpResponse(
                buffer.getvalue(),
                content_type='application/pdf'
            )
            response['Content-Disposition'] = f'attachment; filename="{clean_filename}"'
            response['Content-Length'] = len(buffer.getvalue())
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating WeasyPrint PDF: {e}")
            from django.http import JsonResponse
            return JsonResponse({'success': False, 'error': f'Failed to generate PDF: {str(e)}'})
            
    def _get_css_styles(self):
        """Get CSS styles for the PDF"""
        return """
        @page {
            size: A4;
            margin: 20mm 15mm;
            @top-center {
                content: "";
            }
            @bottom-center {
                content: "Page " counter(page) " of " counter(pages);
                font-size: 10px;
                color: #666;
            }
        }
        
        @page landscape {
            size: A4 landscape;
            margin: 15mm 20mm;
        }
        
        * {
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Arial', sans-serif;
            font-size: 10px;
            line-height: 1.4;
            color: #333;
            margin: 0;
            padding: 0;
        }
        
        .landscape {
            page: landscape;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 2px solid #2c3e50;
            padding-bottom: 15px;
        }
        
        .logo-placeholder {
            width: 120px;
            height: 60px;
            border: 2px dashed #ccc;
            margin: 0 auto 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #999;
            font-size: 12px;
        }
        
        .title {
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
            margin: 10px 0;
        }
        
        .subtitle {
            font-size: 14px;
            color: #666;
            margin-bottom: 5px;
        }
        
        .metadata {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 25px;
        }
        
        .metadata h3 {
            margin: 0 0 10px 0;
            font-size: 14px;
            color: #2c3e50;
            border-bottom: 1px solid #dee2e6;
            padding-bottom: 5px;
        }
        
        .metadata-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
        }
        
        .metadata-item {
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
        }
        
        .metadata-label {
            font-weight: bold;
            color: #495057;
        }
        
        .metadata-value {
            color: #6c757d;
        }
        
        .table-container {
            margin-bottom: 30px;
            page-break-inside: avoid;
        }
        
        .table-title {
            font-size: 16px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 10px;
            border-left: 4px solid #2c3e50;
            padding-left: 10px;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 9px;
            margin-bottom: 15px;
            background: white;
        }
        
        table.wide {
            font-size: 8px;
        }
        
        th {
            background: #2c3e50;
            color: white;
            font-weight: bold;
            padding: 8px 4px;
            text-align: center;
            border: 1px solid #34495e;
            font-size: 9px;
        }
        
        table.wide th {
            padding: 6px 3px;
            font-size: 8px;
        }
        
        td {
            padding: 6px 4px;
            border: 1px solid #dee2e6;
            text-align: left;
        }
        
        table.wide td {
            padding: 4px 3px;
            font-size: 8px;
        }
        
        tr:nth-child(even) {
            background: #f8f9fa;
        }
        
        tr:hover {
            background: #e9ecef;
        }
        
        .numeric {
            text-align: right;
        }
        
        .center {
            text-align: center;
        }
        
        .summary {
            background: #e8f4fd;
            border: 1px solid #bee5eb;
            border-radius: 5px;
            padding: 15px;
            margin-top: 25px;
        }
        
        .summary h3 {
            margin: 0 0 15px 0;
            font-size: 16px;
            color: #2c3e50;
            text-align: center;
        }
        
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
        }
        
        .summary-item {
            text-align: center;
            padding: 15px 10px;  /* Increased padding for better height */
            background: white;
            border-radius: 3px;
            border: 1px solid #bee5eb;
            min-height: 80px;  /* Minimum height to accommodate content */
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        
        .summary-label {
            font-weight: bold;
            color: #495057;
            font-size: 10px;
            margin-bottom: 8px;  /* Increased margin */
            line-height: 1.4;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }
        
        .summary-value {
            font-size: 14px;
            font-weight: bold;
            color: #2c3e50;
            line-height: 1.3;
            word-wrap: break-word;
            overflow-wrap: break-word;
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


def create_weasy_exporter(title, template_type="standard", orientation="portrait"):
    """
    Helper function to create WeasyPrint exporter
    
    Args:
        title: Report title
        template_type: 'standard', 'wide', 'analytics'
        orientation: 'portrait' or 'landscape'
    """
    try:
        return WeasyPrintExporter(title=title, template_type=template_type, orientation=orientation)
    except Exception as e:
        logger.error(f"Error creating WeasyPrint exporter: {e}")
        raise Exception(f"Failed to create WeasyPrint exporter: {str(e)}")


def create_weasy_exporter_for_data(title, data_width="normal"):
    """
    Helper function to create appropriately configured WeasyPrint exporter
    
    Args:
        title: Report title
        data_width: "normal" for portrait, "wide" for landscape
    """
    try:
        if data_width == "wide":
            return WeasyPrintExporter(title=title, template_type="wide", orientation="landscape")
        else:
            return WeasyPrintExporter(title=title, template_type="standard", orientation="portrait")
    except Exception as e:
        logger.error(f"Error creating WeasyPrint exporter: {e}")
        raise Exception(f"Failed to create WeasyPrint exporter: {str(e)}")