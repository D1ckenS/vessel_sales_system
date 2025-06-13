import io
from datetime import datetime
from django.http import HttpResponse
from django.template.loader import get_template
from django.conf import settings
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import logging

# Set up logging
logger = logging.getLogger(__name__)

class ExcelExporter:
    def __init__(self, title="Report"):
        """Initialize Excel exporter with proper error handling"""
        try:
            self.workbook = openpyxl.Workbook()
            # Remove default sheet and create a new one with proper title
            default_sheet = self.workbook.active
            self.workbook.remove(default_sheet)
            
            # Create new sheet with clean title (Excel sheet names max 31 chars)
            clean_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_'))[:31]
            self.worksheet = self.workbook.create_sheet(title=clean_title or "Report")
            
            self.title = title
            self.current_row = 1
            
            # Set up styles
            self._setup_styles()
            
        except Exception as e:
            logger.error(f"ExcelExporter initialization error: {e}")
            raise Exception(f"Failed to initialize Excel exporter: {str(e)}")
    
    def _setup_styles(self):
        """Set up reusable styles"""
        # Title style
        self.title_font = Font(size=16, bold=True, color="1F4E79")
        self.title_alignment = Alignment(horizontal='center', vertical='center')
        self.title_fill = PatternFill(start_color="E7F3FF", end_color="E7F3FF", fill_type="solid")
        
        # Header style
        self.header_font = Font(size=11, bold=True, color="FFFFFF")
        self.header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        self.header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        self.header_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # Data style
        self.data_font = Font(size=10)
        self.data_alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        self.data_border = Border(
            left=Side(style='thin', color="CCCCCC"),
            right=Side(style='thin', color="CCCCCC"),
            top=Side(style='thin', color="CCCCCC"),
            bottom=Side(style='thin', color="CCCCCC")
        )
        
        # Metadata style
        self.metadata_font = Font(size=10, bold=True)
        self.metadata_value_font = Font(size=10)
        
    def add_title(self, title, subtitle=None):
        """Add title with proper column merging based on number of headers"""
        try:
            # Store title info for later use when we know the column count
            self.report_title = title
            self.report_subtitle = subtitle
            
            # Add title row (will be merged later when headers are added)
            self.worksheet[f'A{self.current_row}'] = title
            self.worksheet[f'A{self.current_row}'].font = self.title_font
            self.worksheet[f'A{self.current_row}'].alignment = self.title_alignment
            self.worksheet[f'A{self.current_row}'].fill = self.title_fill
            
            title_row = self.current_row
            self.current_row += 1
            
            # Add subtitle if provided
            if subtitle:
                self.worksheet[f'A{self.current_row}'] = subtitle
                self.worksheet[f'A{self.current_row}'].font = Font(size=12, italic=True, color="666666")
                self.worksheet[f'A{self.current_row}'].alignment = self.title_alignment
                
                subtitle_row = self.current_row
                self.current_row += 1
            
            # Store row numbers for later merging
            self.title_row = title_row
            self.subtitle_row = subtitle_row if subtitle else None
            
            # Add spacing
            self.current_row += 1
            
        except Exception as e:
            logger.error(f"Error adding Excel title: {e}")
            pass
        
    def add_metadata(self, metadata):
        """Add metadata with proper formatting"""
        try:
            if not metadata:
                return
                
            # Metadata header
            self.worksheet[f'A{self.current_row}'].value = "Report Information"
            self.worksheet[f'A{self.current_row}'].font = Font(size=12, bold=True, color="1F4E79")
            self.current_row += 1
            
            # Add metadata rows
            for key, value in metadata.items():
                if key and value is not None:
                    key_cell = self.worksheet[f'A{self.current_row}']
                    value_cell = self.worksheet[f'B{self.current_row}']
                    
                    key_cell.value = str(key) + ":"
                    key_cell.font = self.metadata_font
                    
                    value_cell.value = str(value)
                    value_cell.font = self.metadata_value_font
                    
                    self.current_row += 1
                    
            # Add spacing
            self.current_row += 1
            
        except Exception as e:
            logger.error(f"Error adding metadata: {e}")
            # Don't fail entirely, just skip metadata
            pass
            
    def add_headers(self, headers):
        """Add headers and merge title rows to match header count"""
        try:
            if not headers:
                return
                
            # Add headers
            for col_idx, header in enumerate(headers, 1):
                cell = self.worksheet.cell(row=self.current_row, column=col_idx, value=str(header))
                cell.font = self.header_font
                cell.alignment = self.header_alignment
                cell.fill = self.header_fill
                cell.border = self.border
            
            # Now merge title rows to match the number of header columns
            if hasattr(self, 'title_row'):
                end_column = get_column_letter(len(headers))
                self.worksheet.merge_cells(f'A{self.title_row}:{end_column}{self.title_row}')
                
                if hasattr(self, 'subtitle_row') and self.subtitle_row:
                    self.worksheet.merge_cells(f'A{self.subtitle_row}:{end_column}{self.subtitle_row}')
            
            self.current_row += 1
            
        except Exception as e:
            logger.error(f"Error adding Excel headers: {e}")
            pass
            
    def add_data_rows(self, data_rows):
        """Add data rows with proper formatting and error handling"""
        try:
            if not data_rows:
                # Add "No data" message
                self.worksheet[f'A{self.current_row}'].value = "No data available"
                self.worksheet[f'A{self.current_row}'].font = Font(italic=True, color="666666")
                self.current_row += 1
                return
                
            # Track alternating row colors
            alternate_fill = PatternFill(start_color="F8F9FA", end_color="F8F9FA", fill_type="solid")
            
            for row_idx, row_data in enumerate(data_rows):
                if not row_data:
                    continue
                    
                # Determine if this should be an alternate row
                use_alternate = row_idx % 2 == 1
                
                # Add each cell in the row
                for col_idx, cell_value in enumerate(row_data, 1):
                    try:
                        cell = self.worksheet.cell(row=self.current_row, column=col_idx)
                        
                        # Handle different data types
                        if cell_value is None:
                            cell.value = ''
                        elif isinstance(cell_value, (int, float)):
                            # For numeric values, store as number
                            try:
                                cell.value = float(cell_value)
                                # Format numbers with appropriate decimal places
                                if isinstance(cell_value, float) and abs(cell_value - int(cell_value)) > 0.001:
                                    cell.number_format = '0.000'
                                else:
                                    cell.number_format = '0'
                            except (ValueError, TypeError):
                                cell.value = str(cell_value)
                        else:
                            # For text values, ensure it's a string and not too long
                            str_value = str(cell_value)
                            cell.value = str_value[:32000]  # Excel cell limit
                        
                        # Apply formatting
                        cell.font = self.data_font
                        cell.alignment = self.data_alignment
                        cell.border = self.data_border
                        
                        if use_alternate:
                            cell.fill = alternate_fill
                            
                    except Exception as cell_error:
                        logger.error(f"Error setting cell value: {cell_error}")
                        # Set a default value if individual cell fails
                        cell = self.worksheet.cell(row=self.current_row, column=col_idx)
                        cell.value = "Error"
                        
                self.current_row += 1
                
        except Exception as e:
            logger.error(f"Error adding data rows: {e}")
            # Add error message instead of failing completely
            self.worksheet[f'A{self.current_row}'].value = f"Error loading data: {str(e)}"
            self.current_row += 1
            
    def add_summary(self, summary_data):
        """Add summary statistics with proper formatting"""
        try:
            if not summary_data:
                return
                
            # Add spacing
            self.current_row += 1
            
            # Summary header
            self.worksheet[f'A{self.current_row}'].value = "Summary"
            self.worksheet[f'A{self.current_row}'].font = Font(size=14, bold=True, color="1F4E79")
            self.current_row += 1
            
            # Add summary rows
            for key, value in summary_data.items():
                if key and value is not None:
                    key_cell = self.worksheet[f'A{self.current_row}']
                    value_cell = self.worksheet[f'B{self.current_row}']
                    
                    key_cell.value = str(key) + ":"
                    key_cell.font = Font(bold=True)
                    
                    # Handle numeric values in summary
                    if isinstance(value, (int, float)):
                        try:
                            value_cell.value = float(value)
                            if isinstance(value, float) and abs(value - int(value)) > 0.001:
                                value_cell.number_format = '0.000'
                        except (ValueError, TypeError):
                            value_cell.value = str(value)
                    else:
                        value_cell.value = str(value)
                    
                    value_cell.font = Font(bold=True, color="1F4E79")
                    
                    self.current_row += 1
                    
        except Exception as e:
            logger.error(f"Error adding summary: {e}")
            # Don't fail entirely, just skip summary
            pass

    def add_summary_title(self, title):
        """Add a summary section title"""
        try:
            # Add spacing before summary
            self.current_row += 2
            
            # Add summary title
            self.worksheet[f'A{self.current_row}'] = title
            self.worksheet[f'A{self.current_row}'].font = Font(size=14, bold=True, color="1F4E79")
            self.worksheet[f'A{self.current_row}'].alignment = Alignment(horizontal='left', vertical='center')
            
            self.summary_title_row = self.current_row
            self.current_row += 1
            
        except Exception as e:
            logger.error(f"Error adding summary title: {e}")
            pass

    def add_summary_headers(self, headers):
        """Add summary headers"""
        try:
            if not headers:
                return
                
            # Add summary headers
            for col_idx, header in enumerate(headers, 1):
                cell = self.worksheet.cell(row=self.current_row, column=col_idx, value=str(header))
                cell.font = self.header_font
                cell.alignment = self.header_alignment
                cell.fill = PatternFill(start_color="E3F2FD", end_color="E3F2FD", fill_type="solid")
                cell.border = self.border
            
            # Merge summary title to match summary headers
            if hasattr(self, 'summary_title_row'):
                end_column = get_column_letter(len(headers))
                self.worksheet.merge_cells(f'A{self.summary_title_row}:{end_column}{self.summary_title_row}')
            
            self.current_row += 1
            
        except Exception as e:
            logger.error(f"Error adding summary headers: {e}")
            pass

    def add_summary_data(self, data):
        """Add summary data rows"""
        try:
            if not data:
                return
                
            for row in data:
                for col_idx, value in enumerate(row, 1):
                    cell = self.worksheet.cell(row=self.current_row, column=col_idx, value=str(value) if value is not None else '')
                    cell.border = self.border
                    cell.alignment = Alignment(horizontal='left', vertical='center')
                    
                    # Format numeric columns
                    if col_idx >= 3:  # Quantity and currency columns
                        cell.alignment = Alignment(horizontal='right', vertical='center')
                        if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace('.', '').replace('-', '').isdigit()):
                            cell.number_format = '#,##0.000'
                            
                self.current_row += 1
                
        except Exception as e:
            logger.error(f"Error adding summary data: {e}")
            pass
            
    def auto_adjust_columns(self):
        """Auto-adjust column widths based on content"""
        try:
            for column in self.worksheet.columns:
                if not column:
                    continue
                    
                # Calculate max length for this column
                max_length = 0
                column_letter = get_column_letter(column[0].column)
                
                for cell in column:
                    if cell.value:
                        try:
                            cell_length = len(str(cell.value))
                            if cell_length > max_length:
                                max_length = cell_length
                        except:
                            pass
                
                # Set column width (with limits)
                adjusted_width = min(max_length + 2, 50)  # Max 50 chars
                adjusted_width = max(adjusted_width, 8)   # Min 8 chars
                
                self.worksheet.column_dimensions[column_letter].width = adjusted_width
                
        except Exception as e:
            logger.error(f"Error auto-adjusting columns: {e}")
            # Don't raise exception for this - it's not critical
            
    def get_response(self, filename):
        """Generate HTTP response with Excel file - FIXED VERSION"""
        try:
            # Auto-adjust columns before saving
            self.auto_adjust_columns()
            
            # Clean filename
            clean_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
            if not clean_filename.endswith('.xlsx'):
                clean_filename += '.xlsx'
            
            # Create response using BytesIO buffer - THIS FIXES THE CORRUPTION
            buffer = io.BytesIO()
            self.workbook.save(buffer)
            buffer.seek(0)
            
            # Create HTTP response with proper content
            response = HttpResponse(
                buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{clean_filename}"'
            response['Content-Length'] = len(buffer.getvalue())
                
            return response
            
        except Exception as e:
            logger.error(f"Error generating Excel response: {e}")
            # Return a JSON response instead of failing completely
            from django.http import JsonResponse
            return JsonResponse({'success': False, 'error': f'Failed to generate Excel file: {str(e)}'})


class PDFExporter:
    def __init__(self, title="Report", landscape_mode=False):
        """Initialize PDF exporter with proper error handling"""
        try:
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
            
        except Exception as e:
            logger.error(f"PDFExporter initialization error: {e}")
            raise Exception(f"Failed to initialize PDF exporter: {str(e)}")
        
    def add_title(self, title, subtitle=None):
        """Add title with proper formatting"""
        try:
            self.story.append(Paragraph(str(title) if title is not None else '', self.title_style))
            if subtitle:
                self.story.append(Paragraph(str(subtitle), self.subtitle_style))
            self.story.append(Spacer(1, 20))
        except Exception as e:
            logger.error(f"Error adding PDF title: {e}")
            # Don't fail entirely, just skip title
            pass
        
    def add_metadata(self, metadata):
        """Add metadata table with better sizing"""
        try:
            if not metadata:
                return
                
            data = []
            for key, value in metadata.items():
                if key and value is not None:
                    data.append([str(key) + ":", str(value)])
            
            if not data:
                return
            
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
            
        except Exception as e:
            logger.error(f"Error adding PDF metadata: {e}")
            # Don't fail entirely, just skip metadata
            pass
        
    def add_table(self, headers, data, auto_size_columns=True):
        """Add table with dynamic column sizing and proper width management"""
        try:
            if not data:
                self.story.append(Paragraph("No data available", self.styles['Normal']))
                return
                
            # Prepare table data with proper string conversion
            table_data = []
            if headers:
                table_data.append([str(header) if header is not None else '' for header in headers])
            
            for row in data:
                if row:
                    # Convert all cells to strings and handle None values, truncate long text
                    string_row = []
                    for cell in row:
                        if cell is None:
                            string_row.append('')
                        else:
                            cell_str = str(cell)
                            # Truncate very long text for PDF display
                            string_row.append(cell_str[:50] + '...' if len(cell_str) > 50 else cell_str)
                    table_data.append(string_row)
            
            if not table_data:
                self.story.append(Paragraph("No data available", self.styles['Normal']))
                return
            
            if auto_size_columns and len(table_data[0]) > 0:
                # Calculate optimal column widths
                num_cols = len(table_data[0])
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
                col_width = self.available_width / len(table_data[0])
                col_widths = [col_width] * len(table_data[0])
            
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
            
        except Exception as e:
            logger.error(f"Error adding PDF table: {e}")
            self.story.append(Paragraph(f"Error loading table data: {str(e)}", self.styles['Normal']))
        
    def add_summary(self, summary_data):
        """Add summary section with better layout"""
        try:
            if not summary_data:
                return
                
            self.story.append(Paragraph("Summary", self.header_style))
            
            data = []
            for key, value in summary_data.items():
                if key and value is not None:
                    data.append([str(key) + ":", str(value)])
            
            if not data:
                return
            
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
            
        except Exception as e:
            logger.error(f"Error adding PDF summary: {e}")
            # Don't fail entirely, just skip summary
            pass
        
    def get_response(self, filename):
        """Generate HTTP response with properly sized PDF file - FIXED VERSION"""
        try:
            # Clean filename
            clean_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
            if not clean_filename.endswith('.pdf'):
                clean_filename += '.pdf'
            
            # Create PDF using BytesIO buffer - THIS FIXES THE CORRUPTION
            buffer = io.BytesIO()
            
            # Create PDF with custom page size and margins
            doc = SimpleDocTemplate(
                buffer, 
                pagesize=self.pagesize,
                rightMargin=0.75*inch,
                leftMargin=0.75*inch,
                topMargin=1*inch,
                bottomMargin=0.75*inch
            )
            
            doc.build(self.story)
            buffer.seek(0)
            
            # Create HTTP response with proper content
            response = HttpResponse(
                buffer.getvalue(),
                content_type='application/pdf'
            )
            response['Content-Disposition'] = f'attachment; filename="{clean_filename}"'
            response['Content-Length'] = len(buffer.getvalue())
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating PDF response: {e}")
            # Return a JSON response instead of failing completely
            from django.http import JsonResponse
            return JsonResponse({'success': False, 'error': f'Failed to generate PDF file: {str(e)}'})


def create_pdf_exporter_for_data(title, data_width="normal"):
    """
    Helper function to create appropriately sized PDF exporter
    
    Args:
        title: PDF title
        data_width: "normal" for portrait, "wide" for landscape
    """
    try:
        landscape_mode = data_width == "wide"
        return PDFExporter(title=title, landscape_mode=landscape_mode)
    except Exception as e:
        logger.error(f"Error creating PDF exporter: {e}")
        raise Exception(f"Failed to create PDF exporter: {str(e)}")