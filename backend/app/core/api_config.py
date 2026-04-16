from fastapi.routing import APIRoute


def custom_generate_unique_id(route: APIRoute) -> str:
    """Use the route function name as the operation ID.

    Produces clean SDK method names without tag prefix:
      list_documents → listDocuments
      upload_document → uploadDocument
    """
    return route.name
