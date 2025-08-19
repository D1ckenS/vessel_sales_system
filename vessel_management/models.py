"""
Vessel Management Models
Handles user-vessel assignments and collaborative transfer workflow system.

Based on new_features.txt requirements:
- User-vessel assignment with multi-vessel support for Admins/Managers
- Two-party transfer approval process with edit capabilities
- Inventory status tracking: "Pending Approval" vs "Confirmed by User"
- Complete process history and audit trail
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from vessels.models import Vessel
from products.models import Product


class UserVesselAssignment(models.Model):
    """
    Many-to-many relationship between users and vessels.
    Supports multiple vessel assignments for Admins/Managers.
    SuperUser has automatic access to all vessels.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vessel_assignments')
    vessel = models.ForeignKey(Vessel, on_delete=models.CASCADE, related_name='user_assignments')
    
    # Assignment details
    assigned_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='created_vessel_assignments',
        help_text="User who created this assignment"
    )
    notes = models.TextField(blank=True, help_text="Assignment notes")
    
    # Role-based permissions (future expansion)
    can_make_sales = models.BooleanField(default=True)
    can_receive_inventory = models.BooleanField(default=True)
    can_initiate_transfers = models.BooleanField(default=True)
    can_approve_transfers = models.BooleanField(default=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'vessel']
        ordering = ['vessel__name', 'user__username']
        verbose_name = 'User Vessel Assignment'
        verbose_name_plural = 'User Vessel Assignments'
        indexes = [
            models.Index(fields=['user', 'is_active'], name='vessel_assignment_user_active_idx'),
            models.Index(fields=['vessel', 'is_active'], name='vessel_assignment_vessel_active_idx'),
            models.Index(fields=['assigned_date'], name='vessel_assignment_date_idx'),
        ]
        db_table = 'vessel_management_user_vessel_assignment'
    
    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.user.username} → {self.vessel.name} ({status})"
    
    def clean(self):
        """Validate assignment data"""
        super().clean()
        
        # SuperUser gets automatic permissions
        if self.user and self.user.is_superuser:
            self.can_make_sales = True
            self.can_receive_inventory = True
            self.can_initiate_transfers = True
            self.can_approve_transfers = True
    
    @classmethod
    def get_user_vessels(cls, user):
        """
        Get all vessels a user has access to.
        SuperUser gets access to all active vessels.
        """
        if user.is_superuser:
            return Vessel.objects.filter(active=True)
        
        return Vessel.objects.filter(
            user_assignments__user=user,
            user_assignments__is_active=True,
            active=True
        ).distinct()
    
    @classmethod
    def can_user_access_vessel(cls, user, vessel):
        """Check if user can access a specific vessel"""
        if user.is_superuser:
            return True
        
        return cls.objects.filter(
            user=user,
            vessel=vessel,
            is_active=True
        ).exists()
    
    @classmethod
    def get_assigned_vessel_for_user(cls, user):
        """
        Get the primary assigned vessel for auto-populating "From Vessel".
        Returns the first active assignment or None if multiple/none.
        """
        if user.is_superuser:
            return None  # SuperUser should choose manually
        
        assignments = cls.objects.filter(user=user, is_active=True)
        if assignments.count() == 1:
            return assignments.first().vessel
        return None  # Multiple assignments, let user choose


class TransferWorkflow(models.Model):
    """
    Collaborative transfer workflow system.
    Implements two-party approval process with edit capabilities.
    
    Workflow States:
    1. Created - Transfer initiated by "From User"
    2. Pending Review - Waiting for "To User" to review
    3. Under Review - "To User" is reviewing/editing
    4. Pending Confirmation - "From User" needs to confirm edits
    5. Confirmed - Both parties agreed, ready to execute
    6. Completed - Transfer executed and inventories updated
    """
    
    STATUS_CHOICES = [
        ('created', 'Created'),
        ('pending_review', 'Pending Review'),
        ('under_review', 'Under Review'),
        ('pending_confirmation', 'Pending Confirmation'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Link to existing Transfer model
    base_transfer = models.OneToOneField(
        'transactions.Transfer',
        on_delete=models.CASCADE,
        related_name='workflow',
        help_text="Link to the base transfer record"
    )
    
    # Workflow participants - set only when final approval is made
    from_user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='initiated_transfers',
        help_text="Final approver from the source vessel (set when transfer confirmed)"
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='assigned_transfers',
        help_text="Final approver from the destination vessel (set when transfer confirmed)"
    )
    
    # Workflow status
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='created')
    
    # Two-party confirmation tracking
    from_user_confirmed = models.BooleanField(default=False)
    to_user_confirmed = models.BooleanField(default=False)
    mutual_agreement = models.BooleanField(default=False)
    
    # Edit tracking
    has_edits = models.BooleanField(default=False)
    last_edited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_edited_transfers'
    )
    last_edited_at = models.DateTimeField(null=True, blank=True)
    
    # Completion tracking
    completed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_transfers',
        help_text="User who actually completed/approved the final transfer"
    )
    
    # Workflow timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Process notes
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Transfer Workflow'
        verbose_name_plural = 'Transfer Workflows'
        indexes = [
            models.Index(fields=['status', 'created_at'], name='transfer_workflow_status_created_idx'),
            models.Index(fields=['from_user', 'status'], name='transfer_workflow_from_user_status_idx'),
            models.Index(fields=['to_user', 'status'], name='transfer_workflow_to_user_status_idx'),
            models.Index(fields=['submitted_at'], name='transfer_workflow_submitted_idx'),
        ]
        constraints = [
            # NOTE: Removed different_users constraint to allow same user for cross-vessel operations
            # In vessel-based workflow, users can legitimately have access to multiple vessels
            # Mutual agreement logic - Allow mutual_agreement=True when:
            # 1. TO user confirms without edits (immediate execution), OR
            # 2. Both users confirm when there are edits
            models.CheckConstraint(
                check=models.Q(mutual_agreement=False) | (
                    # Case 1: TO user confirmed without edits
                    models.Q(to_user_confirmed=True, has_edits=False) |
                    # Case 2: Both users confirmed with edits
                    (models.Q(from_user_confirmed=True) & models.Q(to_user_confirmed=True, has_edits=True))
                ),
                name='transfer_workflow_mutual_agreement_logic'
            ),
        ]
        db_table = 'vessel_management_transfer_workflow'
    
    def __str__(self):
        return f"Transfer Workflow: {self.base_transfer.from_vessel.name} → {self.base_transfer.to_vessel.name} ({self.get_status_display()})"
    
    def clean(self):
        """Validate workflow data"""
        super().clean()
        
        # Validate user access to vessels
        if self.from_user and self.base_transfer:
            if not UserVesselAssignment.can_user_access_vessel(
                self.from_user, self.base_transfer.from_vessel
            ):
                raise ValidationError(
                    f"{self.from_user.username} does not have access to {self.base_transfer.from_vessel.name}"
                )
        
        if self.to_user and self.base_transfer:
            if not UserVesselAssignment.can_user_access_vessel(
                self.to_user, self.base_transfer.to_vessel
            ):
                raise ValidationError(
                    f"{self.to_user.username} does not have access to {self.base_transfer.to_vessel.name}"
                )
    
    def submit_for_review(self):
        """Submit transfer for review by To User"""
        if self.status == 'created':
            self.status = 'pending_review'
            self.submitted_at = timezone.now()
            self.save()
            
            # No individual notifications needed - vessel-based notifications via dashboard
            # All users with operations access to the destination vessel will see notifications
    
    def start_review(self, user):
        """Start review process by any authorized vessel user"""
        if self.status == 'pending_review' and self._can_user_review_transfer(user):
            self.status = 'under_review'
            self.reviewed_at = timezone.now()
            # DO NOT assign to_user here - keep it pending until final approval
            self.save()
            
            # Notify original creator (from base_transfer.created_by)
            if self.base_transfer.created_by:
                TransferNotification.objects.create(
                    workflow=self,
                    notification_type='review_started',
                    recipient=self.base_transfer.created_by,
                    title=f"Transfer Review Started",
                    message=f"Transfer review started by {user.username}"
                )
    
    def _can_user_review_transfer(self, user):
        """Check if user can review this transfer based on vessel access"""
        return (
            user.is_superuser or
            UserVesselAssignment.can_user_access_vessel(user, self.base_transfer.to_vessel)
        )
    
    def confirm_by_to_user(self, user):
        """TO vessel user confirms the transfer (with or without edits)"""
        if self.status == 'under_review' and self._can_user_review_transfer(user):
            # Set the to_user to the person who actually confirmed
            if not self.to_user:
                self.to_user = user
                
            self.to_user_confirmed = True
            
            if self.has_edits:
                # If there were edits, FROM vessel users need to confirm
                self.status = 'pending_confirmation'
                
                # Notify original creator about edits
                if self.base_transfer.created_by:
                    TransferNotification.objects.create(
                        workflow=self,
                        notification_type='edits_made',
                        recipient=self.base_transfer.created_by,
                        title=f"Transfer Edited",
                        message=f"Transfer edited by {user.username}. Please review and confirm.",
                        is_urgent=True
                    )
            else:
                # No edits, move directly to confirmed
                self.status = 'confirmed'
                self.confirmed_at = timezone.now()
                self.mutual_agreement = True
                
                # Set the from_user to the original creator since no further approval needed
                if not self.from_user:
                    self.from_user = self.base_transfer.created_by
            
            self.save()
    
    def confirm_by_from_user(self, user):
        """FROM vessel user confirms the edited transfer"""
        # Check if user has access to FROM vessel
        can_confirm = (
            user.is_superuser or
            UserVesselAssignment.can_user_access_vessel(user, self.base_transfer.from_vessel)
        )
        
        if self.status == 'pending_confirmation' and can_confirm:
            # Set the from_user to the person who actually confirmed
            if not self.from_user:
                self.from_user = user
                
            self.from_user_confirmed = True
            self.status = 'confirmed'
            self.confirmed_at = timezone.now()
            self.mutual_agreement = True
            self.save()
            
            # Notify TO User (who made the edits)
            if self.to_user:
                TransferNotification.objects.create(
                    workflow=self,
                    notification_type='transfer_confirmed',
                    recipient=self.to_user,
                    title=f"Transfer Confirmed",
                    message=f"Transfer confirmed by {user.username}. Ready for execution."
                )
    
    def reject_transfer(self, user, reason):
        """Reject the transfer"""
        # Check if user has vessel access to reject this transfer
        can_reject = (
            user.is_superuser or
            user == self.base_transfer.created_by or  # Original creator
            UserVesselAssignment.can_user_access_vessel(user, self.base_transfer.from_vessel) or
            UserVesselAssignment.can_user_access_vessel(user, self.base_transfer.to_vessel)
        )
        
        if can_reject:
            self.status = 'rejected'
            self.rejection_reason = reason
            self.save()
            
            # Notify the original creator if different from rejecting user
            if self.base_transfer.created_by and self.base_transfer.created_by != user:
                TransferNotification.objects.create(
                    workflow=self,
                    notification_type='transfer_rejected',
                    recipient=self.base_transfer.created_by,
                    title=f"Transfer Rejected",
                    message=f"Transfer rejected by {user.username}: {reason}"
                )
    
    def complete_transfer(self, completed_by_user=None):
        """Mark transfer as completed after inventory execution"""
        if self.status == 'confirmed':
            self.status = 'completed'
            self.completed_at = timezone.now()
            if completed_by_user:
                self.completed_by = completed_by_user
            self.save()
            
            # Notify both parties (if they exist)
            notification_recipients = []
            if self.from_user:
                notification_recipients.append(self.from_user)
            if self.to_user and self.to_user != self.from_user:
                notification_recipients.append(self.to_user)
            # Also notify the original creator
            if self.base_transfer.created_by and self.base_transfer.created_by not in notification_recipients:
                notification_recipients.append(self.base_transfer.created_by)
            
            for user in notification_recipients:
                TransferNotification.objects.create(
                    workflow=self,
                    notification_type='transfer_completed',
                    recipient=user,
                    title=f"Transfer Completed",
                    message=f"Transfer has been completed and inventories updated."
                )
    
    @property
    def can_be_edited(self):
        """Check if transfer can still be edited by To User"""
        return self.status == 'under_review'
    
    @property
    def is_pending_action(self):
        """Check if transfer is waiting for user action"""
        return self.status in ['pending_review', 'pending_confirmation']
    
    @property
    def current_pending_user(self):
        """Get the user who needs to take action (or vessel type for vessel-based workflow)"""
        if self.status == 'pending_review':
            return f"{self.base_transfer.to_vessel.name} vessel users"
        elif self.status == 'pending_confirmation':
            return f"{self.base_transfer.from_vessel.name} vessel users"
        return None


class TransferItemEdit(models.Model):
    """
    Tracks edits to individual transfer items (products and quantities).
    Allows "To User" to modify transfer quantities during review.
    """
    workflow = models.ForeignKey(
        TransferWorkflow,
        on_delete=models.CASCADE,
        related_name='item_edits'
    )
    
    # Product and quantity details
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    original_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        help_text="Original quantity requested by From User"
    )
    edited_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        help_text="New quantity set by To User"
    )
    
    # Edit details
    edited_by = models.ForeignKey(User, on_delete=models.PROTECT)
    edited_at = models.DateTimeField(auto_now_add=True)
    edit_reason = models.TextField(help_text="Reason for quantity change")
    
    class Meta:
        ordering = ['-edited_at']
        verbose_name = 'Transfer Item Edit'
        verbose_name_plural = 'Transfer Item Edits'
        indexes = [
            models.Index(fields=['workflow', 'product'], name='transfer_edit_workflow_product_idx'),
            models.Index(fields=['edited_by', 'edited_at'], name='transfer_edit_user_date_idx'),
        ]
        constraints = [
            # Ensure positive quantities
            models.CheckConstraint(
                check=models.Q(original_quantity__gt=0),
                name='transfer_edit_positive_original_quantity'
            ),
            models.CheckConstraint(
                check=models.Q(edited_quantity__gt=0),
                name='transfer_edit_positive_edited_quantity'
            ),
            # Ensure there's actually a change
            models.CheckConstraint(
                check=~models.Q(original_quantity=models.F('edited_quantity')),
                name='transfer_edit_quantity_changed'
            ),
        ]
        db_table = 'vessel_management_transfer_item_edit'
    
    def __str__(self):
        return f"Edit: {self.product.name} - {self.original_quantity} → {self.edited_quantity}"
    
    @property
    def quantity_change(self):
        """Calculate the quantity change"""
        return self.edited_quantity - self.original_quantity
    
    @property
    def is_increase(self):
        """Check if this is a quantity increase"""
        return self.edited_quantity > self.original_quantity
    
    @property
    def is_decrease(self):
        """Check if this is a quantity decrease"""
        return self.edited_quantity < self.original_quantity


class TransferApprovalHistory(models.Model):
    """
    Complete audit trail for transfer workflow process.
    Tracks all actions and status changes for transparency.
    """
    workflow = models.ForeignKey(
        TransferWorkflow,
        on_delete=models.CASCADE,
        related_name='approval_history'
    )
    
    ACTION_TYPES = [
        ('created', 'Transfer Created'),
        ('submitted', 'Submitted for Review'),
        ('review_started', 'Review Started'),
        ('quantities_edited', 'Quantities Edited'),
        ('confirmed_by_to_user', 'Confirmed by To User'),
        ('confirmed_by_from_user', 'Confirmed by From User'),
        ('rejected', 'Transfer Rejected'),
        ('completed', 'Transfer Completed'),
        ('cancelled', 'Transfer Cancelled'),
        ('comment_added', 'Comment Added'),
    ]
    
    action_type = models.CharField(max_length=25, choices=ACTION_TYPES)
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    performed_at = models.DateTimeField(auto_now_add=True)
    
    # Action details
    notes = models.TextField(blank=True)
    previous_status = models.CharField(max_length=25, blank=True)
    new_status = models.CharField(max_length=25, blank=True)
    
    # Additional data (JSON for flexibility)
    action_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional action-specific data"
    )
    
    class Meta:
        ordering = ['-performed_at']
        verbose_name = 'Transfer Approval History'
        verbose_name_plural = 'Transfer Approval Histories'
        indexes = [
            models.Index(fields=['workflow', 'performed_at'], name='transfer_history_workflow_date_idx'),
            models.Index(fields=['action_type', 'performed_at'], name='transfer_history_action_date_idx'),
            models.Index(fields=['performed_by'], name='transfer_history_user_idx'),
        ]
        db_table = 'vessel_management_transfer_approval_history'
    
    def __str__(self):
        return f"{self.get_action_type_display()} by {self.performed_by.username} at {self.performed_at}"


class TransferNotification(models.Model):
    """
    Real-time notification system for transfer workflow events.
    Enables user alerts and process tracking as per requirements.
    """
    workflow = models.ForeignKey(
        TransferWorkflow,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    
    NOTIFICATION_TYPES = [
        ('transfer_submitted', 'Transfer Submitted'),
        ('review_started', 'Review Started'),
        ('edits_made', 'Quantities Edited'),
        ('transfer_confirmed', 'Transfer Confirmed'),
        ('transfer_rejected', 'Transfer Rejected'),
        ('transfer_completed', 'Transfer Completed'),
        ('comment_added', 'Comment Added'),
        ('reminder', 'Reminder'),
    ]
    
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transfer_notifications')
    
    # Notification content
    title = models.CharField(max_length=200)
    message = models.TextField()
    action_url = models.URLField(blank=True, help_text="URL to relevant action page")
    
    # Status
    is_read = models.BooleanField(default=False)
    is_urgent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Transfer Notification'
        verbose_name_plural = 'Transfer Notifications'
        indexes = [
            models.Index(fields=['recipient', 'is_read'], name='transfer_notification_user_read_idx'),
            models.Index(fields=['notification_type', 'created_at'], name='transfer_notification_type_date_idx'),
            models.Index(fields=['is_urgent', 'is_read'], name='transfer_notification_urgent_read_idx'),
        ]
        db_table = 'vessel_management_transfer_notification'
    
    def __str__(self):
        status = "Read" if self.is_read else "Unread"
        return f"{self.get_notification_type_display()} for {self.recipient.username} ({status})"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()
    
    @classmethod
    def get_unread_count(cls, user):
        """Get count of unread notifications for user"""
        return cls.objects.filter(recipient=user, is_read=False).count()
    
    @classmethod
    def get_pending_transfers(cls, user):
        """Get transfers pending action from user"""
        return cls.objects.filter(
            recipient=user,
            is_read=False,
            notification_type__in=['transfer_submitted', 'edits_made']
        ).order_by('-created_at')


class InventoryLotStatus(models.Model):
    """
    Tracks inventory lot status during transfer workflow.
    Implements "Pending Approval" vs "Confirmed by User" states.
    """
    inventory_lot = models.ForeignKey(
        'transactions.InventoryLot',
        on_delete=models.CASCADE,
        related_name='transfer_statuses'
    )
    workflow = models.ForeignKey(
        TransferWorkflow,
        on_delete=models.CASCADE,
        related_name='lot_statuses'
    )
    
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('pending_approval', 'Pending Approval'),
        ('confirmed_by_from_user', 'Confirmed by From User'),
        ('confirmed_by_to_user', 'Confirmed by To User'),
        ('transferred', 'Transferred'),
    ]
    
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='available')
    quantity_affected = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        help_text="Quantity involved in this transfer"
    )
    
    # Confirmation tracking
    confirmed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who confirmed this lot status"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['inventory_lot', 'workflow']
        ordering = ['-created_at']
        verbose_name = 'Inventory Lot Status'
        verbose_name_plural = 'Inventory Lot Statuses'
        indexes = [
            models.Index(fields=['status', 'created_at'], name='lot_status_status_created_idx'),
            models.Index(fields=['inventory_lot', 'status'], name='lot_status_lot_status_idx'),
            models.Index(fields=['workflow'], name='lot_status_workflow_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity_affected__gt=0),
                name='lot_status_positive_quantity'
            ),
        ]
        db_table = 'vessel_management_inventory_lot_status'
    
    def __str__(self):
        return f"Lot {self.inventory_lot.id} - {self.get_status_display()} ({self.quantity_affected} units)"
    
    def mark_as_pending(self):
        """Mark lot as pending approval"""
        self.status = 'pending_approval'
        self.save()
    
    def confirm_by_user(self, user):
        """Confirm lot status by user"""
        if user == self.workflow.from_user:
            self.status = 'confirmed_by_from_user'
        elif user == self.workflow.to_user:
            self.status = 'confirmed_by_to_user'
        
        self.confirmed_by = user
        self.confirmed_at = timezone.now()
        self.save()
    
    def mark_as_transferred(self):
        """Mark lot as successfully transferred"""
        self.status = 'transferred'
        self.save()