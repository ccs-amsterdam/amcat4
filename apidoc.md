# AmCAT4 API Documentation

Please see the tabs below for the various API endpoints.
See also the GitHub pages for the <a href="https://github.com/ccs-amsterdam/amcat4">API/backend</a>
and client bindings for <a href="https://github.com/ccs-amsterdam/amcat4apiclient">Python</a>
and <a href="https://github.com/ccs-amsterdam/amcat4r">R</a>.


##  Querying


API Endpoints for querying


### POST /index/<index>/aggregate</h2>

<pre>

    Construct an aggregate query. POST body should be a json dict:
    {'axes': [{'field': .., ['interval': ..]}, ...],
     'filters': <filters, see query endpoint>
     }
    Will return a json list of lists [<axis-1-name>, ..., _n]
    
</pre>

### GET /index/<index>/query</h2>

<pre>

    Query (or list) documents in this index. GET request parameters:
    q - Elastic query string. Argument may be repeated for multiple queries (treated as OR)
    sort - Comma separated list of fields to sort on, e.g. id,date:desc
    fields - Comma separated list of fields to return
    per_page - Number of results per page
    page - Page to fetch
    scroll - If given, create a new scroll_id to download all results in subsequent calls
    scroll_id - Get the next batch from this id.
    Any additional GET parameters are interpreted as filters, and can be
    field=value for a term query, or field__xxx=value for a range query, with xxx in gte, gt, lte, lt
    Note that dates can use relative queries, see elasticsearch 'date math'
    In case of conflict between field names and (other) arguments, you may prepend a field name with __
    If your field names contain __, it might be better to use POST queries
    highlight - if true, add highlight tags <em>
    annotations - if true, also return _annotations with query matches as annotations
    
</pre>

### POST /index/<index>/query</h2>

<pre>

    List or query documents in this index. POST body should be a json dict structured as follows (all keys optional):
    
    
    {
        # for optional param in {sort, per_page, page, scroll, scroll_id, highlight, annotations}
        param: value,   

        # select fields
        fields: field                                    ## single field
        fields: [field1, field2]                         ## multiple fields
     
        # elastic queries. 
        'queries':  query,                               ## single query
        'queries': [query1, query2],                     ## OR without labels
        'queries': {label1: query1, label2: query2}      ## OR with labels

        # filters 
        'filters': {field: value},                       ## exact value
                   {field: [value1, value2]},            ## OR   
                   {field: {gt(e): value, lt(e): value}  ## range or multiple
                   {field: {values: [v1,v2]}             ## can also use values inside dict
        }        
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

### PUT /index/<ix></h2>

<pre>

    Modify the index. Currently only supports modifying guest_role
    POST data should be json containing the changed values (i.e. guest_role)
    
</pre>

### GET /index/<ix></h2>

<pre>

    Modify the index. Currently only supports modifying guest_role
    POST data should be json containing the changed values (i.e. guest_role)
    
</pre>

### DELETE /index/<ix></h2>

<pre>

    Delete the index.
    
</pre>

### POST /index/<ix>/documents</h2>

<pre>

    Upload documents to this server
    JSON payload should be a list of documents with at least a title, date, text and any optional attributes
    Note: The unique elastic ID will be the hash of title, date, text and url.
    
</pre>

### GET /index/<ix>/documents/<docid></h2>

<pre>

    Get a single document by id
    GET request parameters:
    fields - Comma separated list of fields to return (default: all fields)
    
</pre>

### PUT /index/<ix>/documents/<docid></h2>

<pre>

    Update a document
    PUT request body should be a json {field: value} mapping of fields to update
    
</pre>

### GET /index/<ix>/fields</h2>

<pre>

    Get the fields (columns) used in this index
    
</pre>

### GET /index/<ix>/fields/<field>/values</h2>

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

### GET /users/<email></h2>

<pre>

    View the current user. Users can view themselves, writer can view others
    
</pre>

### DELETE /users/<email></h2>

<pre>

    Delete the given user. Users can delete themselves, admin can delete everyone, and writer can delete non-admin
    
</pre>

### PUT /users/<email></h2>

<pre>

    Modify the given user.
    Users can modify themselves (but not their role), admin can change everyone, and writer can change non-admin.
    
</pre>

### GET /users/all</h2>

<pre>
None
</pre>


