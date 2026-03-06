import os 
def X(s:str, x:bool):
    if x:
        return f'X({s})'
    return s


def get_relative_file_path(directory_path, file_path):
    """
    Computes the relative path of a file relative to a given directory.

    Args:
        directory_path (str): The output directory path (can be absolute or relative).
        file_path (str): The absolute path to the file.

    Returns:
        str: The relative path from directory_path to file_path.
    """
    # Step 1: Ensure the directory path is absolute
    # If it's already absolute, os.path.abspath returns it unchanged.
    # If it's relative, it resolves it based on the current working directory.
    abs_dir = os.path.abspath(directory_path)

    # Step 2: Ensure the file path is absolute (per requirements)
    abs_file = os.path.abspath(file_path)

    # Step 3: Compute the relative path
    # os.path.relpath(target, start) returns a relative file path to target from
    # the start directory.
    relative_path = os.path.relpath(abs_file, abs_dir)

    return relative_path