import maya.cmds as cmds
import maya.mel as mel

# the name of the yeti graph editor window
YETI_WIN = 'pgYetiGraphPanelWindow'


def get_sel_grooms():
    """
    Returns groom shape nodes from selection
    """
    sel = cmds.ls(sl=1)
    grooms = []
    for obj in sel:
        shape = str()

        if cmds.objectType(obj) == 'transform':
            shape = cmds.listRelatives(obj, shapes=1)[0]
        else:
            shape = obj

        if cmds.objectType(shape) == 'pgYetiGroom':
            grooms.append(shape)

    return grooms


def groom_to_curves(groom):
    # unfortunately, the convert to curves command doesn't return anything
    # so we have to get all the curves before and after the command is run
    # to get the new curves
    before_curves = cmds.ls(type='nurbsCurve')
    cmds.select(groom)
    mel.eval('pgYetiCommand -convertToCurves {}'.format(groom))
    after_curves = cmds.ls(type='nurbsCurve')
    new_curves = [c for c in after_curves if c not in before_curves]
    new_curves_transforms = [
        cmds.listRelatives(c, parent=1)[0] for c in new_curves
    ]
    new_curve_dict = {}
    if new_curves:
        transform = cmds.listRelatives(new_curves[0], parent=1)[0]
        guide_set = cmds.listConnections(transform, type='objectSet')[0]
        cmds.sets(new_curves_transforms, add=guide_set)
        new_curve_dict[guide_set] = new_curves

    return new_curve_dict


def yetis_from_groom(groom):
    """
    Get a list of all Yeti nodes that a groom is connected to
    """
    yetis = cmds.listConnections(groom, type='pgYetiMaya')
    return yetis


def create_node(yeti, type, name=None):
    """
    Wrapper for the graph creation mel command
    """
    node = mel.eval('pgYetiGraph -create -type "{type}" {yeti}'.format(
        type=type, yeti=yeti))

    # disconnect the inputs
    mel.eval('pgYetiGraph -disconnect 0 -node {node} {yeti}'.format(node=node,
                                                                    yeti=yeti))

    # rename the node if a name is given
    if name:
        mel.eval('pgYetiGraph -node "{node}" -rename "{name}" {yeti}'.format(
            node=node, name=name, yeti=yeti))
        node = name

    # force graph refresh to prevent crashing if another node is created
    refresh_graph()

    return node


def get_imports(yeti, type, selection=None):
    """
    List all import nodes of a certain type in a given Yeti node

    Optionally specify the selection to filter imports that only have that
    string specified in the selection field.
    """
    type_dict = {
        'geometry': 0,
        'groom': 1,
        'guides': 2,
        'feather': 3,
        'braid': 4,
    }

    imp_nodes = mel.eval(
        'pgYetiGraph -listNodes -type "import" {yeti}'.format(yeti=yeti))

    type_nodes = []
    for imp_node in imp_nodes:
        curr_type = mel.eval(
            'pgYetiGraph -node {node} -param "type" -getParamValue {yeti}'.
            format(node=imp_node, yeti=yeti))
        if curr_type == type_dict[type]:
            if selection:
                curr_selection = mel.eval(
                    'pgYetiGraph -node {node} -param "geometry" -getParamValue {yeti}'
                    .format(node=imp_node, yeti=yeti))
                if curr_selection == selection:
                    type_nodes.append(imp_node)
            else:
                type_nodes.append(imp_node)

    return type_nodes


def set_param(yeti, param, node, val, type):
    """
    Wrapper for param setting command
    """
    type_dict = {
        'scalar': 'setParamValueScalar',
        'string': 'setParamValueString ',
        'vector': 'setParamValueVector',
        'expression': 'setParamValueExpr',
        'boolean': 'setParamValueBoolean',
    }

    mel.eval('pgYetiGraph -node {node} -param "{param}" -{type} {val} {yeti}'.
             format(node=node,
                    param=param,
                    type=type_dict[type],
                    val=val,
                    yeti=yeti))

    refresh_graph()


def connect_nodes(yeti, from_node, to_node, input):
    """
    Wrapper for node connecting command
    """
    mel.eval('pgYetiGraph -node {from_node} -connect {to_node} {input} {yeti}'.
             format(from_node=from_node,
                    to_node=to_node,
                    input=input,
                    yeti=yeti))

    refresh_graph()


def refresh_graph():
    """
    Opens and then closes the graph editor to help with stability when creting nodes
    """
    mel.eval('pgYetiTearOffGraphPanel')
    if YETI_WIN in cmds.lsUI(type='window'):
        cmds.deleteUI(YETI_WIN)


def guided_grooms():
    """
    For a selected groom, create a graph in all it's Yeti nodes that guides
    the groom strands by guides created from the groom.

    Connect the output of this new network to all nodes (except grow nodes)
    that the groom was connected to.

    A new user attribute is also added to the Yeti node to control a blend
    between the groom and the 'guided groom'
    """
    # store the state of the graph window
    graph_open = 0
    if YETI_WIN in cmds.lsUI(type='window'):
        refresh_graph()
        graph_open = 1

    for groom in get_sel_grooms():
        # yeti nodes
        yeti_nodes = yetis_from_groom(groom)
        # convert the groom to curves
        groom_dict = groom_to_curves(groom)

        for yeti in yeti_nodes:
            # get all of the geometry nodes
            geo_nodes = get_imports(yeti, 'geometry')
            # get all of the groom nodes
            groom_nodes = get_imports(yeti, 'groom', groom)
            # if we can't find an explicit groom node, use a wildcard groom
            if not groom_nodes:
                groom_nodes = get_imports(yeti, 'groom', '*')

            if not groom_nodes:
                cmds.warning(
                    'Yeti node: {yeti} has no grooms imported in the graph, skipping...'
                    .format(yeti=yeti))

            elif len(geo_nodes) != 1:
                cmds.warning(
                    'Yeti node: {yeti} has several geometry import nodes, skipping...'
                    .format(yeti=yeti))

            # if we've got at least one groom node and only one geo node, let's go!
            else:
                # add the guide sets to the yeti nodes
                mel.eval('pgYetiAddGuideSet("{guide_set}", "{yeti}")'.format(
                    guide_set=groom_dict.keys()[0], yeti=yeti))

                # import the guides into the yeti node
                guide_import = create_node(yeti, 'import',
                                           groom_dict.keys()[0])

                # switch the import mode to guides
                set_param(yeti, 'type', guide_import, 2, 'scalar')

                # set the selection to the guide set
                set_param(yeti, 'geometry', guide_import,
                          groom_dict.keys()[0], 'string')

                # set guide attrs
                cmds.setAttr(
                    groom_dict.keys()[0] + '.maxNumberOfGuideInfluences', 1)
                for guide in groom_dict[groom_dict.keys()[0]]:
                    cmds.setAttr(guide + '.weight', 10)
                    cmds.setAttr(guide + '.tipAttraction', 1)
                    cmds.setAttr(guide + '.baseAttraction', 1)

                for groom_node in groom_nodes:
                    # convert the grooms
                    convert_node = create_node(yeti, 'convert')
                    connect_nodes(yeti, groom_node, convert_node, 0)
                    connect_nodes(yeti, geo_nodes[0], convert_node, 1)

                    # create guide node
                    guide_node = create_node(yeti, 'guide')
                    connect_nodes(yeti, convert_node, guide_node, 0)
                    connect_nodes(yeti, guide_import, guide_node, 1)

                    # set up blending
                    blend_node = create_node(yeti, 'blend')
                    connect_nodes(yeti, convert_node, blend_node, 0)
                    connect_nodes(yeti, guide_node, blend_node, 1)


    # show the graph?
    if graph_open:
        mel.eval('pgYetiTearOffGraphPanel')
