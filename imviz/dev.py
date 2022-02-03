"""
Because the automatic code reloading cannot reload the __main__ module,
we provide a module here, which can launch and reload a given class.

This frees the library user from providing such a main module themselves.

For specific needs not covered by this simple implementation, you may use
this module as a reference for your own (development) main module.
"""

import sys
import time
import argparse
import traceback

# i like this
from pydoc import locate

import imviz as viz


def loop(cls, func_name):

    viz.configure_ini_path(sys.modules[cls.__module__])

    obj = cls()
    func = getattr(obj, func_name)

    broken = False

    while viz.wait(vsync=True):

        if viz.update_autoreload():
            broken = False

        try:
            if not broken:
                func()
            else:
                time.sleep(0.5)
        except Exception:
            traceback.print_exc()
            broken = True


def main():

    parser = argparse.ArgumentParser(
            description="Launch a class with automatic code reloading")

    parser.add_argument(
            "class_name",
            type=str,
            help="the name of the class to instantiate")

    parser.add_argument(
            "func_name",
            type=str,
            help="the name of the method to call")

    args = parser.parse_args()

    cls = locate(args.class_name)
    if cls is None:
        print(f"Could not find function {args.func_name}")
        return

    loop(cls, args.func_name)


if __name__ == "__main__":
    main()
