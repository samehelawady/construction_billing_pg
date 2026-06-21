(function($) {
    'use strict';

    $(document).ready(function() {
        var projectSelect = $('#id_project');
        var invoiceSelect = $('#id_invoice');
        var originalOptions = invoiceSelect.html();

        function filterInvoices(projectId) {
            if (!projectId) {
                invoiceSelect.empty().append('<option value="">---------</option>');
                invoiceSelect.prop('disabled', true);
                return;
            }

            invoiceSelect.prop('disabled', true);

            $.ajax({
                url: '/admin/billing/invoice-autocomplete/',
                data: {
                    project: projectId,
                    term: ''
                },
                dataType: 'json',
                success: function(data) {
                    var currentVal = invoiceSelect.val();
                    invoiceSelect.empty();

                    // Add empty option
                    invoiceSelect.append($('<option>', {
                        value: '',
                        text: '---------'
                    }));

                    // Add fetched options
                    $.each(data.results, function(i, item) {
                        var option = $('<option>', {
                            value: item.id,
                            text: item.text
                        });
                        if (item.id == currentVal) {
                            option.prop('selected', true);
                        }
                        invoiceSelect.append(option);
                    });

                    invoiceSelect.prop('disabled', false);
                },
                error: function() {
                    // Fallback: restore original options filtered by project
                    invoiceSelect.html(originalOptions);
                    invoiceSelect.find('option').each(function() {
                        var optionProject = $(this).data('project');
                        if (optionProject && optionProject != projectId) {
                            $(this).remove();
                        }
                    });
                    invoiceSelect.prop('disabled', false);
                }
            });
        }

        // Filter on project change
        projectSelect.on('change', function() {
            filterInvoices($(this).val());
        });

        // Initial state
        if (!projectSelect.val()) {
            invoiceSelect.prop('disabled', true);
        } else {
            filterInvoices(projectSelect.val());
        }
    });
})(django.jQuery);