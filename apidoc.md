# AmCAT4 API Documentation

Please see the tabs below for the various API endpoints.
See also the GitHub pages for the <a href="https://github.com/ccs-amsterdam/amcat4">API/backend</a>
and client bindings for <a href="https://github.com/ccs-amsterdam/amcat4apiclient">Python</a>
and <a href="https://github.com/ccs-amsterdam/amcat4r">R</a>.

Note: To generate this documentation, run `python -m amcat4 document`


##  Querying


API Endpoints for querying


### POST /index/&lt;index&gt;/aggregate</h2>

<pre>

    Construct an aggregate query. POST body should be a json dict with axes and/or aggregations keys,
    and optional filters and queries keys:
    :axes: list of dicts containing field and optional interval: [{&#39;field&#39;: .., [&#39;interval&#39;: ..]}, ...],
    :aggregations: list of dicts containing field, function, and optional name: [{field, function, [name]}, ...]
    :filters: see POST /query endpoint,
    :queries: see POST /query endpoint,
     }

    For example, to get average views per week per publisher
    {
     &#39;axes&#39;: [{&#39;field&#39;: &#39;date&#39;, &#39;interval&#39;:&#39;week&#39;}, {&#39;field&#39;: &#39;publisher&#39;}],
     &#39;aggregations&#39;: [{&#39;field&#39;: &#39;views&#39;, &#39;function&#39;: &#39;avg&#39;}]
    }

    Returns a JSON object {data: [{axis1, ..., n, aggregate1, ...}, ...], meta: {axes: [...], aggregations: [...]}
    
</pre>

### POST /index/&lt;index&gt;/query</h2>

<pre>

    List or query documents in this index. POST body should be a json dict structured as follows (all keys optional):


    {
        # for optional param in {sort, per_page, page, scroll, scroll_id, highlight, annotations}
        &lt;param&gt;: value,

        # select fields
        &#39;fields&#39;: field                                    ## single field
        &#39;fields&#39;: [field1, field2]                         ## multiple fields

        # elastic queries.
        &#39;queries&#39;:  query,                               ## single query
        &#39;queries&#39;: [query1, query2],                     ## OR without labels
        &#39;queries&#39;: {label1: query1, label2: query2}      ## OR with labels

        # filters
        &#39;filters&#39;: {field: value},                       ## exact value
                   {field: [value1, value2]},            ## OR
                   {field: {gt(e): value, lt(e): value}  ## range or multiple
                   {field: {values: [v1,v2]}             ## can also use values inside dict
        }
    }

    Returns a JSON object {data: [...], meta: {total_count, per_page, page_count, page|scroll_id}}
    }

    
</pre>


## Documents


API Endpoints for document and index management


### GET /index/</h2>

<pre>

    List index from this server. Returns a list of dicts containing name, role, and guest attributes
    
</pre>

### POST /index/</h2>

<pre>

    Create a new index, setting the current user to admin (owner).
    POST data should be json containing name and optional guest_role
    
</pre>

### PUT /index/&lt;ix&gt;</h2>

<pre>

    Modify the index. Currently only supports modifying guest_role
    POST data should be json containing the changed values (i.e. guest_role)
    
</pre>

### GET /index/&lt;ix&gt;</h2>

<pre>

    Modify the index. Currently only supports modifying guest_role
    POST data should be json containing the changed values (i.e. guest_role)
    
</pre>

### DELETE /index/&lt;ix&gt;</h2>

<pre>

    Delete the index.
    
</pre>

### POST /index/&lt;ix&gt;/documents</h2>

<pre>

    Upload documents to this server.
    JSON payload should contain a `documents` key, and may contain a `columns` key:
    {
      &#34;documents&#34;: [{&#34;title&#34;: .., &#34;date&#34;: .., &#34;text&#34;: .., ...}, ...],
      &#34;columns&#34;: {&lt;field&gt;: &lt;type&gt;, ...}
    }
    Returns a list of ids for the uploaded documents
    
</pre>

### GET /index/&lt;ix&gt;/documents/&lt;docid&gt;</h2>

<pre>

    Get a single document by id
    GET request parameters:
    fields - Comma separated list of fields to return (default: all fields)
    
</pre>

### PUT /index/&lt;ix&gt;/documents/&lt;docid&gt;</h2>

<pre>

    Update a document
    PUT request body should be a json {field: value} mapping of fields to update
    
</pre>

### GET /index/&lt;ix&gt;/fields</h2>

<pre>

    Get the fields (columns) used in this index
    returns a json array of {name, type} objects
    
</pre>

### POST /index/&lt;ix&gt;/fields</h2>

<pre>

    Set the field types used in this index
    POST body should be a dict of {field: type}
    
</pre>

### GET /index/&lt;ix&gt;/fields/&lt;field&gt;/values</h2>

<pre>

    Get the fields (columns) used in this index
    
</pre>


## Authentication


AmCAT4 can use either Basic or Token-based authentication.
A client can request a token with basic authentication and store that token for future requests.


### GET /auth/token/</h2>

<pre>

    Create a new token for the authenticated user
    
</pre>


## Users


AmCAT4 can use either Basic or Token-based authentication.
A client can request a token with basic authentication and store that token for future requests.


### POST /users/</h2>

<pre>

    Create a new user. Request body should be a json with email, password, and optional (global) role
    
</pre>

### GET /users/&lt;email&gt;</h2>

<pre>

    View the current user. Users can view themselves, writer can view others
    
</pre>

### DELETE /users/&lt;email&gt;</h2>

<pre>

    Delete the given user. Users can delete themselves, admin can delete everyone, and writer can delete non-admin
    
</pre>

### PUT /users/&lt;email&gt;</h2>

<pre>

    Modify the given user.
    Users can modify themselves (but not their role), admin can change everyone, and writer can change non-admin.
    
</pre>

### GET /users/all</h2>

<pre>
None
</pre>


