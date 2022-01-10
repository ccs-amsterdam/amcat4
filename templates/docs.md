# AmCAT4 API Documentation

Please see the tabs below for the various API endpoints.
See also the GitHub pages for the <a href="https://github.com/ccs-amsterdam/amcat4">API/backend</a>
and client bindings for <a href="https://github.com/ccs-amsterdam/amcat4apiclient">Python</a>
and <a href="https://github.com/ccs-amsterdam/amcat4r">R</a>.

Note: To generate this documentation, run `python -m amcat4 document`

{% for group in groups %}
## {{group.title}}

{{group.doc}}
{% for rule in group.rules %}
### {{rule.method}} {{rule.rule| escape }}</h2>

<pre>
{{ rule.docstring | escape }}
</pre>
{% endfor %}
{% endfor %}