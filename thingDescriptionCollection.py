class ThingDescriptionCollection:
    tds = None
    
    def __init__(self, tds):
        self.tds = tds

    def getActionInput(self, actionName):
        for td in self.tds:
            if "actions" not in td:
                continue

            for actName, actValue in td["actions"].items():
                if actName != actionName:
                    continue
                
                if "input" in actValue:
                    return actValue["input"]
                else:
                    return {}

    def getEventData(self, eventName):
        for td in self.tds:
            if "events" not in td:
                continue

            for evtName, evtValue in td["events"].items():
                if evtName != eventName:
                    continue

                if "description" in evtValue["data"]:
                    del evtValue["data"]["description"]

                if "unit" in evtValue["data"]:
                    del evtValue["data"]["unit"]

                if "enum" in evtValue["data"]:
                    del evtValue["data"]["enum"]

                if "properties" not in evtValue["data"]:
                    return evtValue["data"]

                for property in evtValue["data"]["properties"].values():
                    if "description" in property:
                        del property["description"]

                    if "unit" in property:
                        del property["unit"]

                    if "enum" in property:
                        del property["enum"]

                return evtValue["data"]

    def getActionOutput(self, actionName):
        for td in self.tds:
            if "actions" not in td:
                continue

            for actName, actValue in td["actions"].items():
                if actName != actionName:
                    continue

                if "output" not in actValue:
                    continue

                if "description" in actValue["output"]:
                    del actValue["output"]["description"]

                if "enum" in actValue["output"]:
                    del actValue["output"]["enum"]

                return actValue["output"]
        return None
    
    def getPropertyValue(self, propertyName):
        for td in self.tds:
            if "properties" not in td:
                continue

            for propName, propValue in td["properties"].items():
                if propName != propertyName:
                    continue

                propertyReturn = {}
                propertyReturn["type"] = propValue["type"]

                if "properties" in propValue:
                    propertyReturn["properties"] = propValue["properties"]

                return propertyReturn
        return None
