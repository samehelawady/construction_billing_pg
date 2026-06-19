(function($) {
    'use strict';

    $(document).ready(function() {
        var projectField = $('#id_project');
        var boqField = $('#id_boq_item');
        var initialProject = projectField.val();

        function updateBOQItems(projectId, preserveSelection) {
            if (!projectId) {
                boqField.html('<option value="">---------</option>');
                return;
            }

            var currentVal = preserveSelection ? boqField.val() : null;

            $.ajax({
                url: '/admin/billing/boqitem/get-by-project/',
                data: {project_id: projectId},
                dataType: 'json',
                success: function(data) {
                    var options = '<option value="">---------</option>';
                    $.each(data, function(index, item) {
                        var selected = (currentVal && item.id == currentVal) ? ' selected' : '';
                        options += '<option value="' + item.id + '"' + selected + '>' +
                                   escapeHtml(item.text) + '</option>';
                    });
                    boqField.html(options);
                    boqField.trigger('change');
                },
                error: function() {
                    console.error('Failed to load BOQ items for project ' + projectId);
                }
            });
        }

        function escapeHtml(text) {
            var div = document.createElement('div');
            div.appendChild(document.createTextNode(text));
            return div.innerHTML;
        }

        // On project change, reload BOQ items
        projectField.on('change', function() {
            updateBOQItems($(this).val(), false);
        });

        // On page load: if project is selected but BOQ is empty, populate it
        // (This handles the "save and continue editing" case)
        if (initialProject && boqField.find('option').length <= 1) {
            updateBOQItems(initialProject, true);
        }
    });
})(django.jQuery);