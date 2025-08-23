class ThingDescriptionCollection:
    tds = None
    
    def __init__(self, tds):
        self.tds = tds

    def getActionInput(self, actionName):
        for td in self.tds:
            if "actions" not in td:
                continue

            for k, v in td["actions"].items():
                if k == actionName:
                    return v["input"]
                
    def getEventData(self, eventName):
        for i in self.tds:
            if "events" not in i:
                continue

            for k, v in i["events"].items():
                if k != eventName:
                    continue

                if "description" in v["data"]:
                    del v["data"]["description"]

                if "unit" in v["data"]:
                    del v["data"]["unit"]

                if "enum" in v["data"]:
                    del v["data"]["enum"]

                if "properties" not in v["data"]:
                    return v["data"]
                
                for j in v["data"]["properties"].values():
                    if "description" in j:
                        del j["description"]

                    if "unit" in j:
                        del j["unit"]

                    if "enum" in j:
                        del j["enum"]
                
                return v["data"]
                
    def getActionOutput(self, actionName):
        for td in self.tds:
            if "actions" not in td:
                continue

            for k, v in td["actions"].items():
                if k != actionName:
                    continue
                
                if "output" not in v:
                    continue

                if "description" in v["output"]:
                    del v["output"]["description"]

                if "enum" in v["output"]:
                    del v["output"]["enum"]
                    
                return v["output"]
        return None
    
    def getPropertyValue(self, propertyName):
        for td in self.tds:
            if "properties" not in td:
                continue

            for k, v in td["properties"].items():
                if k != propertyName:
                    continue

                a = {}
                a["type"] = v["type"]

                if "properties" in v:
                    a["properties"] = v["properties"]
                
                return a
        return None
