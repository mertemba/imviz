import os
import sys


try:
    from cppimviz import *
except ModuleNotFoundError:
    sys.path.append(os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "../build"))
    from cppimviz import *
    print("Using development imviz")


def configure_ini_path(module):

    print(module)

    if not hasattr(module, "__file__"):
        return

    main_file_name = os.path.basename(module.__file__).rsplit(".")[0]
    ini_path = os.path.join(
            os.path.abspath(os.path.dirname(module.__file__)),
            "imviz_" + main_file_name + ".ini")

    set_ini_path(ini_path)
    load_ini(ini_path)


import __main__
configure_ini_path(__main__)


from imviz.common import *
from imviz.autogui import render as autogui
