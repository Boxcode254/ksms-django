from django.urls import path

from .views import (
    DeletedInvoiceListView,
    DeletedPaymentListView,
    FeeStructureCreateView,
    FeeArrearListView,
    FeeArrearExportCsvView,
    FeeStructureListView,
    FeeStructureUpdateView,
    InvoiceCreateView,
    InvoiceDetailView,
    InvoiceListView,
    InvoiceUpdateView,
    MpesaCallbackView,
    MpesaSTKPushInitView,
    PaymentCreateView,
    PaymentReceiptDownloadView,
    ReminderPolicyUpdateView,
    RestoreInvoiceView,
    RestorePaymentView,
    SendArrearReminderView,
    SendBulkArrearReminderView,
)

app_name = "finance"

urlpatterns = [
    path("finance/fee-structures/", FeeStructureListView.as_view(), name="feestructure-list"),
    path("finance/fee-structures/create/", FeeStructureCreateView.as_view(), name="feestructure-create"),
    path("finance/fee-structures/<int:pk>/edit/", FeeStructureUpdateView.as_view(), name="feestructure-update"),
    path("finance/invoices/", InvoiceListView.as_view(), name="invoice-list"),
    path("finance/invoices/create/", InvoiceCreateView.as_view(), name="invoice-create"),
    path("finance/invoices/<int:pk>/", InvoiceDetailView.as_view(), name="invoice-detail"),
    path("finance/invoices/<int:pk>/edit/", InvoiceUpdateView.as_view(), name="invoice-update"),
    path("finance/invoices/<int:invoice_pk>/payments/new/", PaymentCreateView.as_view(), name="payment-create"),
    path("finance/invoices/<int:invoice_pk>/payments/stk/init/", MpesaSTKPushInitView.as_view(), name="mpesa-stk-init"),
    path("finance/payments/<int:pk>/receipt/", PaymentReceiptDownloadView.as_view(), name="payment-receipt"),
    path("finance/arrears/", FeeArrearListView.as_view(), name="fee-arrear-list"),
    path("finance/arrears/reminder-policy/", ReminderPolicyUpdateView.as_view(), name="reminder-policy-update"),
    path("finance/arrears/export/csv/", FeeArrearExportCsvView.as_view(), name="fee-arrear-export-csv"),
    path("finance/arrears/remind/", SendBulkArrearReminderView.as_view(), name="fee-arrear-remind-bulk"),
    path("finance/arrears/<int:pk>/remind/", SendArrearReminderView.as_view(), name="fee-arrear-remind"),
    path("finance/payments/mpesa/callback/", MpesaCallbackView.as_view(), name="mpesa-callback"),
    path("finance/invoices/deleted/", DeletedInvoiceListView.as_view(), name="invoice-deleted-list"),
    path("finance/payments/deleted/", DeletedPaymentListView.as_view(), name="payment-deleted-list"),
    path("finance/invoices/<int:pk>/restore/", RestoreInvoiceView.as_view(), name="invoice-restore"),
    path("finance/payments/<int:pk>/restore/", RestorePaymentView.as_view(), name="payment-restore"),
]
