// Expense BOQ and sub-category filter
(function($) {
    $(document).ready(function() {
        var $project = $('#id_project');
        var $boqItem = $('#id_boq_item');
        var $category = $('#id_category');
        var $subCategory = $('#id_sub_category');

        function updateBOQItems() {
            var projectId = $project.val();
            if (!projectId) {
                $boqItem.html('<option value="">---------</option>');
                return;
            }
            $.get('/admin/billing/boqitem/get-by-project/', {project_id: projectId}, function(data) {
                var options = '<option value="">---------</option>';
                for (var i = 0; i < data.length; i++) {
                    options += '<option value="' + data[i].id + '">' + data[i].text + '</option>';
                }
                $boqItem.html(options);
            });
        }

        function updateSubCategories() {
            var categoryId = $category.val();
            if (!categoryId) {
                $subCategory.html('<option value="">---------</option>');
                return;
            }
            $.get('/admin/billing/expensecategory/subexpense/get-by-category/', {category_id: categoryId}, function(data) {
                var options = '<option value="">---------</option>';
                for (var i = 0; i < data.length; i++) {
                    options += '<option value="' + data[i].id + '">' + data[i].text + '</option>';
                }
                $subCategory.html(options);
            });
        }

        $project.on('change', updateBOQItems);
        $category.on('change', updateSubCategories);
    });
})(django.jQuery);
