try:
    import canopen
except ImportError:
    import canopen_asyncio as canopen  # type: ignore[no-redef]

ObjectDictionary = canopen.objectdictionary.ObjectDictionary
Variable = canopen.objectdictionary.Variable

od = ObjectDictionary()
var_node = Variable("Node ID", 0x2000, 0)
var_node.data_type = 5  # UNSIGNED8
var_node.access_type = "rw"
od.add_object(var_node)

print(od[0x2000].name)
