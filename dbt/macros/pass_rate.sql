{% macro pass_rate(passed_column, total_expression='count(*)') %}
    round(100.0 * sum({{ passed_column }}) / nullif({{ total_expression }}, 0), 2)
{% endmacro %}
