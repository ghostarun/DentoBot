# Toggle the stamped development-only first-complete route mode (default off).
facade._dev_first_complete_route = not bool(getattr(facade, "_dev_first_complete_route", False))
result = {"dev_first_complete_route": facade._dev_first_complete_route}
