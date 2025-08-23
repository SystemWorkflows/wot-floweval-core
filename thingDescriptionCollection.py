class ThingDescriptionCollection:
    tds = None
    
    def __init__(self,tds):
        self.tds = tds

    def getActionInput(self, actionName):
        for i in self.tds:
            if "actions" in i:
                for k,v in i["actions"].items():
                    if k == actionName:
                        print("k: ", k)
                        return v["input"]
                
    def getEventData(self, eventName):
        for i in self.tds:
            if "events" in i:
                for k,v in i["events"].items():
                    if k == eventName:
                        if "description" in v["data"]:
                            del v["data"]["description"]
                        if "unit" in v["data"]:
                            del v["data"]["unit"]
                        if "enum" in v["data"]:
                            del v["data"]["enum"]
                        if "properties" in v["data"]:
                            for j in v["data"]["properties"].values():
                                if "description" in j:
                                    del j["description"]
                                if "unit" in j:
                                    del j["unit"]
                                if "enum" in j:
                                    del j["enum"]
                        return v["data"]
                
    def getActionOutput(self, actionName):
        for i in self.tds:
            if "actions" in i:
                for k,v in i["actions"].items():
                    if k == actionName:
                        print("k: ", k)
                        if "output" in v:
                            if "description" in v["output"]:
                                del v["output"]["description"]
                            if "enum" in v["output"]:
                                del v["output"]["enum"]
                            return v["output"]
        return None
    
    def getPropertyValue(self,propertyName):
        for i in self.tds:
            if "properties" in i:
                for k,v in i["properties"].items():
                    if k == propertyName:
                        a = {}
                        a["type"] = v["type"]
                        if "properties" in v:
                            a["properties"] = v["properties"]
                        return a
        return None
