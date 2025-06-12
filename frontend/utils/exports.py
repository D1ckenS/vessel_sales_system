import io
from datetime import datetime
from django.http import HttpResponse
from django.template.loader import get_template
from django.conf import settings
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

class ExcelExporter:
    def __init__(self, title="Report"):
        self.workbook = openpyxl.Workbook()
        self.worksheet = self.workbook.active
        self.title = title
        self.current_row = 1
        
    def add_title(self, title, subtitle=None):
        """Add title and subtitle to the worksheet"""
        self.worksheet.merge_cells(f'A{self.current_row}:H{self.current_row}')
        title_cell = self.worksheet[f'A{self.current_row}']
        title_cell.value = title
        title_cell.font = Font(size=16, bold=True)
        title_cell.alignment = Alignment(horizontal='center')
        self.current_row += 1
        
        if subtitle:
            self.worksheet.merge_cells(f'A{self.current_row}:H{self.current_row}')
            subtitle_cell = self.worksheet[f'A{self.current_row}']
            subtitle_cell.value = subtitle
            subtitle_cell.font = Font(size=12)
            subtitle_cell.alignment = Alignment(horizontal='center')
            self.current_row += 1
            
        self.current_row += 1  # Add spacing
        
    def add_metadata(self, metadata):
        """Add metadata like export date, filters, etc."""
        for key, value in metadata.items():
            self.worksheet[f'A{self.current_row}'] = f"{key}:"
            self.worksheet[f'B{self.current_row}'] = str(value)
            self.worksheet[f'A{self.current_row}'].font = Font(bold=True)
            self.current_row += 1
        self.current_row += 1  # Add spacing
        
    def add_headers(self, headers):
        """Add table headers"""
        for col_num, header in enumerate(headers, 1):
            cell = self.worksheet.cell(row=self.current_row, column=col_num)
            cell.value = header
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            cell.alignment = Alignment(horizontal='center')
            cell.border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
        self.current_row += 1
        
    def add_data_rows(self, data_rows):
        """Add data rows"""
        for row_data in data_rows:
            for col_num, value in enumerate(row_data, 1):
                cell = self.worksheet.cell(row=self.current_row, column=col_num)
                cell.value = value
                cell.border = Border(
                    left=Side(style='thin'),
                    right=Side(style='thin'),
                    top=Side(style='thin'),
                    bottom=Side(style='thin')
                )
                if isinstance(value, (int, float)) and col_num > 1:
                    cell.alignment = Alignment(horizontal='right')
            self.current_row += 1
            
    def add_summary(self, summary_data):
        """Add summary statistics"""
        self.current_row += 1
        self.worksheet[f'A{self.current_row}'] = "Summary"
        self.worksheet[f'A{self.current_row}'].font = Font(bold=True, size=14)
        self.current_row += 1
        
        for key, value in summary_data.items():
            self.worksheet[f'A{self.current_row}'] = f"{key}:"
            self.worksheet[f'B{self.current_row}'] = value
            self.worksheet[f'A{self.current_row}'].font = Font(bold=True)
            self.current_row += 1
            
    def auto_adjust_columns(self):
        """Auto-adjust column widths"""
        for column_cells in self.worksheet.columns:
            length = max(len(str(cell.value or "")) for cell in column_cells)
            self.worksheet.column_dimensions[get_column_letter(column_cells[0].column)].width = min(length + 2, 50)
            
    def get_response(self, filename):
        """Generate HTTP response with Excel file"""
        self.auto_adjust_columns()
        
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Save workbook to response
        self.workbook.save(response)
        return response

class PDFExporter:
    def __init__(self, title="Report", landscape_mode=False):
        self.title = title
        self.landscape_mode = landscape_mode
        self.styles = getSampleStyleSheet()
        self.story = []
        
        # Determine page size and orientation
        if self.landscape_mode:
            self.pagesize = landscape(A4)  # Landscape A4: 842 x 595 points
            self.available_width = 842 - 2*inch  # ~650 points available
        else:
            self.pagesize = A4  # Portrait A4: 595 x 842 points
            self.available_width = 595 - 2*inch  # ~450 points available
        
        # Custom styles with better sizing
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=20,
            alignment=1,  # Center alignment
            textColor=colors.HexColor('#0f4c75')
        )
        
        self.subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=self.styles['Normal'],
            fontSize=12,
            spaceAfter=15,
            alignment=1,
            textColor=colors.HexColor('#6c757d')
        )
        
        self.header_style = ParagraphStyle(
            'CustomHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=10,
            textColor=colors.HexColor('#0f4c75')
        )
        
    def add_title(self, title, subtitle=None):
        """Add title with proper formatting"""
        self.story.append(Paragraph(title, self.title_style))
        if subtitle:
            self.story.append(Paragraph(subtitle, self.subtitle_style))
        self.story.append(Spacer(1, 20))
        
    def add_metadata(self, metadata):
        """Add metadata table with better sizing"""
        if not metadata:
            return
            
        data = [[key + ":", str(value)] for key, value in metadata.items()]
        
        # Calculate column widths based on available space
        col1_width = self.available_width * 0.35
        col2_width = self.available_width * 0.65
        
        table = Table(data, colWidths=[col1_width, col2_width])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8f9fa')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        self.story.append(table)
        self.story.append(Spacer(1, 20))
        
    def add_table(self, headers, data, auto_size_columns=True):
        """Add table with dynamic column sizing and proper width management"""
        if not data:
            self.story.append(Paragraph("No data available", self.styles['Normal']))
            return
            
        # Prepare table data with proper string conversion
        table_data = [headers]
        for row in data:
            # Convert all cells to strings and handle None values
            string_row = [str(cell) if cell is not None else '' for cell in row]
            table_data.append(string_row)
        
        if auto_size_columns and len(headers) > 0:
            # Calculate optimal column widths
            num_cols = len(headers)
            col_widths = []
            
            # Calculate content-based widths
            for col_idx in range(num_cols):
                max_content_length = 0
                for row in table_data:
                    if col_idx < len(row):
                        content_length = len(str(row[col_idx]))
                        max_content_length = max(max_content_length, content_length)
                
                # Convert to actual width
                # Base width calculation: 6 points per character + padding
                min_width = 60  # Minimum 60 points (~0.83 inch)
                estimated_width = max_content_length * 6 + 20  # 6 points per char + padding
                col_widths.append(max(min_width, estimated_width))
            
            # Scale down if total width exceeds available space
            total_width = sum(col_widths)
            if total_width > self.available_width:
                scale_factor = self.available_width / total_width
                col_widths = [w * scale_factor for w in col_widths]
                
            # Ensure minimum readable width
            min_readable_width = 50
            col_widths = [max(w, min_readable_width) for w in col_widths]
            
        else:
            # Equal width columns
            col_width = self.available_width / len(headers)
            col_widths = [col_width] * len(headers)
        
        # Create table
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # Enhanced table styling
        table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f4c75')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            
            # Data rows styling
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            
            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            
            # Handle text wrapping
            ('WORDWRAP', (0, 0), (-1, -1), 'LTR'),
        ]))
        
        self.story.append(table)
        self.story.append(Spacer(1, 20))
        
    def add_summary(self, summary_data):
        """Add summary section with better layout"""
        if not summary_data:
            return
            
        self.story.append(Paragraph("Summary", self.header_style))
        
        data = [[key + ":", str(value)] for key, value in summary_data.items()]
        
        # Use smaller width for summary table (centered)
        col1_width = self.available_width * 0.4
        col2_width = self.available_width * 0.35
        
        table = Table(data, colWidths=[col1_width, col2_width])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e3f2fd')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        self.story.append(table)
        self.story.append(Spacer(1, 20))
        
    def get_response(self, filename):
        """Generate HTTP response with properly sized PDF file"""
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Create PDF with custom page size and margins
        doc = SimpleDocTemplate(
            response, 
            pagesize=self.pagesize,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=1*inch,
            bottomMargin=0.75*inch
        )
        
        doc.build(self.story)
        return response


def create_pdf_exporter_for_data(title, data_width="normal"):
    """
    Helper function to create appropriately sized PDF exporter
    
    Args:
        title: PDF title
        data_width: "normal" for portrait, "wide" for landscape
    """
    landscape_mode = data_width == "wide"
    return PDFExporter(title=title, landscape_mode=landscape_mode)