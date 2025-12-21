from fastapi.routing import APIRoute


def custom_generate_unique_id(route: APIRoute) -> str:
    """
    Generate clean operation IDs for SDK method names.
    Format: {tag}-{function_name}
    Example: jobs-list_jobs → SDK: jobsListJobs()
    """
    if route.tags:
        return f"{route.tags[0]}-{route.name}"
    return route.name
