import io
from datetime import datetime
from django.http import HttpResponse
from django.template.loader import get_template
from django.conf import settings
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
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
    def __init__(self, title="Report"):
        self.title = title
        self.styles = getSampleStyleSheet()
        self.story = []
        
        # Custom styles
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1  # Center
        )
        
        self.subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=20,
            alignment=1  # Center
        )
        
    def add_title(self, title, subtitle=None):
        """Add title and subtitle"""
        self.story.append(Paragraph(title, self.title_style))
        if subtitle:
            self.story.append(Paragraph(subtitle, self.subtitle_style))
        self.story.append(Spacer(1, 20))
        
    def add_metadata(self, metadata):
        """Add metadata table"""
        data = [[key + ":", str(value)] for key, value in metadata.items()]
        table = Table(data, colWidths=[2*inch, 4*inch])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        self.story.append(table)
        self.story.append(Spacer(1, 20))
        
    def add_table(self, headers, data_rows):
        """Add data table"""
        # Prepare table data
        table_data = [headers] + data_rows
        
        # Create table
        table = Table(table_data)
        
        # Style the table
        table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#366092')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            
            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        
        self.story.append(table)
        self.story.append(Spacer(1, 20))
        
    def add_summary(self, summary_data):
        """Add summary section"""
        self.story.append(Paragraph("Summary", self.styles['Heading2']))
        
        data = [[key + ":", str(value)] for key, value in summary_data.items()]
        table = Table(data, colWidths=[2*inch, 2*inch])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        self.story.append(table)
        
    def get_response(self, filename):
        """Generate HTTP response with PDF file"""
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Create PDF
        doc = SimpleDocTemplate(response, pagesize=A4)
        doc.build(self.story)
        
        return response