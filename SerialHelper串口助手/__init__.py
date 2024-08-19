# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import bpy
import serial
import serial.tools.list_ports
import threading
import time
import math
from bpy.types import Context
import re
import queue
import random


bl_info = {
    "name": "Serial Helper/串口助手",
    "author": "SFY",
    "description": "在blender中使用串口进行通讯/A tool to help with serial communication.",
    "blender": (2, 80, 0),
    "version": (1, 0, 1),
    "location": "View3D > Tool Shelf",
    "warning": "",
    "category": "Generic"
}

# 定义属性组


class SerialConnection:
    def __init__(self, port, baudrate, bytesize, parity, stopbits):
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.serial = serial.Serial(port, baudrate, bytesize, parity, stopbits)


class ServoDataSender:
    def __init__(self, serial_connection):
        self.serial_connection = serial_connection

    def pack_servo_data(self, servos):
        # servos 是一个包含多个舵机数据的列表，每个元素是一个 (编号, 角度) 的元组
        data_str = ''
        for servo_id, angle in servos:
            data_str += f's{servo_id:03d}a{angle:.2f}'
        return data_str

    def collect_and_send_servo_data(self):
        arm1_data = math.degrees(bpy.data.objects['Armature'].pose.bones['arm1'].rotation_euler[2]) + 90
        arm2_data = -math.degrees(bpy.data.objects['Armature'].pose.bones['arm2'].rotation_euler[0]) + 90
        arm3_data = math.degrees(bpy.data.objects['Armature'].pose.bones['arm3'].rotation_euler[0]) + 140
        servos = [(1, arm1_data), (2, arm2_data), (3, arm3_data)]
        packed_data = self.pack_servo_data(servos)
        self.serial_connection.serial.write(packed_data.encode())
        print(packed_data)  # 打印输出数据


def extract_value(input_str, var_name):
    # 定义正则表达式模式，用于匹配特定变量名和其后的浮点数（包括负数）
    pattern = fr"{re.escape(var_name)}=([-+]?\d*\.\d+|\d+)"

    # 使用re.search查找第一个匹配项
    match = re.search(pattern, input_str)

    # 检查是否找到匹配项
    if match:
        # 返回匹配的浮点数
        return float(match.group(1))
    else:
        # 如果没有找到匹配项，返回None或合适的提示信息
        return None


data_queue = queue.Queue()


class SerialHelperThread(threading.Thread):
    def __init__(self, serial_connection):
        threading.Thread.__init__(self)
        self.serial_connection = serial_connection
        self.should_terminate = False
        self.data_queue = data_queue

    def run(self):
        while not self.should_terminate:
            if not bpy.context.scene.serial_helper.StopReceiving:
                try:
                    data = self.serial_connection.serial.readline()
                    data = data.decode(bpy.context.scene.serial_helper.Encoding, errors='ignore').strip()
                    self.data_queue.put(data)
                    bpy.app.timers.register(serial_data_update)
                except Exception as e:
                    print(f"数据接受失败: {e}")


def serial_data_update():
    scene = bpy.context.scene
    data = data_queue.get()
    item = scene.serial_helper.serial_data_list.add()
    item.index = scene.serial_helper.serial_data_count
    item.data_string = data
    for mapping_item in scene.serial_helper.serial_data_matching_list:
        print(mapping_item.matching_data_value)
        if extract_value(data, mapping_item.matching_data_name) != None:
            mapping_item.matching_data_value = extract_value(data, mapping_item.matching_data_name)

# 移除多余的项
    if len(scene.serial_helper.serial_data_list) > scene.serial_helper.serial_data_max_count:
        for i in range(len(scene.serial_helper.serial_data_list) - scene.serial_helper.serial_data_max_count):
            scene.serial_helper.serial_data_list.remove(i)

    scene.serial_helper.serial_data_count += 1
    scene.frame_set(scene.frame_current)  # 刷新界面
    # if bpy.context and bpy.context.screen:
    #     for a in bpy.context.screen.areas:
    #         a.tag_redraw()


def open_serial_port():
    scence = bpy.context.scene
    if scence.serial_helper.use_input_serial_port:
        port = scence.serial_helper.user_input_serial_port
    else:
        port = scence.serial_helper.serial_ports
    baudrate = scence.serial_helper.baudrate
    bytesize = scence.serial_helper.bytesize
    parity = scence.serial_helper.parity
    stopbits = scence.serial_helper.stopbits
    if not "serial_connection" in bpy.app.driver_namespace:
        bpy.app.driver_namespace["serial_connection"] = SerialConnection(port, baudrate, int(bytesize), parity, int(stopbits))
        serial_thread = SerialHelperThread(bpy.app.driver_namespace["serial_connection"])
        serial_thread.start()
        bpy.app.driver_namespace["serial_thread"] = serial_thread
        print(f"成功打开串口{port}")
    else:
        print("串口已经打开")


class SerialHelpPanel(bpy.types.Panel):
    bl_label = "Serial Helper"
    bl_idname = "VIEW3D_PT_serial_help"  # 通常与视图3D面板关联的ID
    bl_space_type = 'VIEW_3D'  # VIEW_3D 是3D视图的上下文
    bl_region_type = 'UI'  # UI 区域类型通常用于侧边的工具面板
    bl_category = "串口助手"  # 面板的类别

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column()
        col.operator("test.operator", text="Test Operator")
        row = col.row(align=True)
        row.scale_y = 2  # 调整按钮高度
        row.label(text="端口名：")
        row.alignment = 'LEFT'
        row1 = row.row()
        row1.scale_x = 2
        row1.alignment = 'EXPAND'
        if scene.serial_helper.use_input_serial_port:
            row1.prop(scene.serial_helper, "user_input_serial_port", text="")
        else:
            row1.prop(context.scene.serial_helper, "serial_ports", text="")
        row1.prop(scene.serial_helper, "use_input_serial_port", text="", icon_value=197)
        row2 = col.row()
        row2.alert = context.scene.serial_helper.serial_is_open  # 设置警告状态，使按钮变红
        row2.scale_y = 2  # 调整按钮高度
        row2.operator("serial.switch_operator", text="打开串口" if context.scene.serial_helper.serial_is_open == False else "关闭串口")

        box = col.box()
        box.prop(context.scene.serial_helper, "baudrate")
        box.prop(context.scene.serial_helper, "bytesize")
        box.prop(context.scene.serial_helper, "stopbits")
        box.prop(context.scene.serial_helper, "parity")


class ReceivingSettingsPanel(bpy.types.Panel):
    bl_label = '接收设置'
    bl_idname = 'VIEW_3D_PT_ReceivingSettings'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'scene'

    bl_order = 0

    bl_parent_id = 'VIEW3D_PT_serial_help'
    bl_ui_units_x = 0

    @ classmethod
    def poll(cls, context):
        return not (False)

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        row = box.row()
        row.scale_y = 2
        row.prop(context.scene.serial_helper, "Encoding")
        col = row.column()
        col.prop(context.scene.serial_helper, "StopReceiving", text="暂停" if context.scene.serial_helper.StopReceiving else "正在接收", icon_value=498 if context.scene.serial_helper.StopReceiving else 495)


class SerialDataDisplayPanel(bpy.types.Panel):
    bl_label = "接受数据显示"
    bl_idname = "VIEW_3D_PT_DataDisplayPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "scene"

    bl_parent_id = 'VIEW_3D_PT_ReceivingSettings'
    bl_ui_units_x = 0

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.template_list("SERIAL_UL_DataList", "", scene.serial_helper, "serial_data_list", scene.serial_helper, "serial_data_index")
        row = layout.row()
        # row.operator("serial_data.add_item", text="添加项")
        # row.operator("serial_data.delete_item", text="删除项")
        row.operator("serial_data.clear_items", text="清空数据", icon='TRASH')
        row.prop(scene.serial_helper, "serial_data_max_count", text="显示数量")


class SerialDataItemProperties(bpy.types.PropertyGroup):
    index: bpy.props.IntProperty(default=0)
    data_string: bpy.props.StringProperty()


class SERIAL_UL_DataList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # item是列表中的每一项，这里我们假设item有两个属性：index和data_string
        row = layout.row(align=True)
        row.alignment = 'LEFT'.upper()
        row.label(text=f"{item.index}")
        row2 = row.row(align=True)
        row2.alignment = 'Expand'.upper()
        row2.scale_x = 1.5
        row2.prop(item, "data_string", text="")


class SerialDataMatchingProperties(bpy.types.PropertyGroup):
    matching_data_name: bpy.props.StringProperty(name="匹配数据名称", default="匹配数据名称")
    matching_data_value: bpy.props.FloatProperty(name="匹配值", default=0)


class SERIAL_UL_DataMatchingList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.alignment = 'EXPAND'
        row.prop(item, "matching_data_name", text="数据名称")
        row.prop(item, "matching_data_value", text="匹配值")
        row.operator("serial_data_matching.copy_driver", text="", icon='COPYDOWN', emboss=False).index = index


class SerialHelperDataMatchingPanel(bpy.types.Panel):
    bl_label = "数据匹配"
    bl_idname = "VIEW_3D_PT_DataMatchingPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "scene"

    bl_parent_id = 'VIEW_3D_PT_ReceivingSettings'
    bl_ui_units_x = 0

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        row = layout.row()
        row.template_list("SERIAL_UL_DataMatchingList", "", scene.serial_helper, "serial_data_matching_list", scene.serial_helper, "serial_data_matching_index")
        col = row.column(align=True)
        col.operator("serial_data_matching.add_item", icon_value=31, text="")
        col.operator("serial_data_matching.delete_item", icon_value=32, text="")

        box = layout.box()
        row2 = box.row()
        # row2.prop(scene.serial_helper, "serial_data_matching_update_use", text="更新数据用")
        # row2.operator("serial_data_matching.update_driver", icon_value=692, text="刷新更新数据驱动器")
        col2 = box.column()
        col2.scale_y = 0.5
        col2.label(text="数据格式:  匹配数据名称=匹配值 如: x=100")
        col2.label(text="获取数据方式,右键,复制为新驱动器,然后在数值上右键,粘贴驱动器")
        col2.label(text="节点编辑器中驱动器不能刷新的话就复制上面那个驱动器到随便一个节点上")


class SendDataSerialPanel(bpy.types.Panel):
    bl_label = "发送数据"
    bl_idname = "VIEW_3D_PT_SendDataInSerialPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "scene"

    bl_parent_id = 'VIEW3D_PT_serial_help'
    bl_ui_units_x = 0

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        box = layout.box()
        row = box.row()
        row.scale_y = 2
        row.prop(scene.serial_helper, "serial_send_data", text="")
        row2 = box.row()
        col = row2.column()
        col.alignment = 'Center'.upper()
        col.scale_x = 1.5
        col.scale_y = 2
        col.prop(scene.serial_helper, "is_newline", text="换行", icon_value=745)
        col2 = row2.column()
        col2.scale_y = 2
        col2.operator("serial.send_data_operator", text="发送数据", icon='FILE_TICK')
        row3 = box.row()
        row3.prop(scene.serial_helper, "is_auto_send", text="定时发送", icon_value=118)
        row3.prop(scene.serial_helper, "auto_send_interval", text="发送间隔(s)")


class SendVariablePathItem(bpy.types.PropertyGroup):
    variable_name: bpy.props.StringProperty(name="Variable Name", default="")
    data_path: bpy.props.StringProperty(name="Data Path", default="")


class SERIAL_UL_SendVariable_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.alignment = 'LEFT'
        row.label(text=f"{index} ")
        row2 = row.row(align=True)
        row2.alignment = 'EXPAND'
        row2.prop(item, "variable_name", text="")
        row2.prop(item, "data_path", text="")


class SerialHelperSendVariablePanel(bpy.types.Panel):
    bl_label = "变量列表"
    bl_idname = "VIEW_3D_PT_SendVariablePanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "scene"

    bl_parent_id = 'VIEW_3D_PT_SendDataInSerialPanel'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row()
        row.template_list("SERIAL_UL_SendVariable_list", "", scene.serial_helper, "Send_variable_list", scene.serial_helper, "Send_variable_index")

        col = row.column(align=True)
        col.operator("serial.add_variable_operator", icon='ADD', text="")
        col.operator("serial.remove_variable_operator", icon='REMOVE', text="")


class SerialFastMessagePanle(bpy.types.Panel):
    bl_label = "快速消息"
    bl_idname = "VIEW_3D_PT_FastMessagePanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "scene"

    bl_parent_id = 'VIEW_3D_PT_SendDataInSerialPanel'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        row = layout.row()
        row.template_list("SERIAL_UL_FastMessage_list", "", scene.serial_helper, "fast_message_list", scene.serial_helper, "fast_message_index")
        col = row.column(align=True)
        col.operator("serial.add_fast_message_operator", icon='ADD', text="")
        col.operator("serial.remove_fast_message_operator", icon='REMOVE', text="")


class SerialFastMessageItem(bpy.types.PropertyGroup):
    message_name: bpy.props.StringProperty(name="名称", default="")
    message: bpy.props.StringProperty(name="消息", default="")


class SERIAL_UL_FastMessage_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.alignment = 'LEFT'
        row.scale_x = 2
        row.label(text=f"{index+1}:")
        row.prop(item, "message_name", text="")
        row2 = row.row(align=True)
        row2.scale_x = 1.5
        row2.alignment = 'EXPAND'
        row2.prop(item, "message", text="")
        row2.operator("serial.send_fast_message_operator", text="", icon_value=415, emboss=False).index = index


class ClearSerialDataItemsOperator(bpy.types.Operator):
    bl_idname = "serial_data.clear_items"
    bl_label = "Clear All Serial Data Items"

    def execute(self, context):
        scene = context.scene
        scene.serial_helper.serial_data_list.clear()
        scene.serial_helper.serial_data_count = 1
        return {'FINISHED'}


class AddSerialDataMatchingItemOperator(bpy.types.Operator):

    bl_idname = "serial_data_matching.add_item"
    bl_label = "Add Serial Data Matching Item"

    def execute(self, context):
        scene = context.scene
        item = scene.serial_helper.serial_data_matching_list.add()
        scene.serial_helper.serial_data_matching_index = len(scene.serial_helper.serial_data_matching_list) - 1
        item.matching_data_name = "数据名称"
        item.matching__data_value = 0
        return {'FINISHED'}


class RemoveSerialDataMatchingItemOperator(bpy.types.Operator):

    bl_idname = "serial_data_matching.delete_item"
    bl_label = "Delete Serial Data Matching Item"

    def execute(self, context):
        scene = context.scene
        if scene.serial_helper.serial_data_matching_list:
            scene.serial_helper.serial_data_matching_list.remove(scene.serial_helper.serial_data_matching_index)
            if scene.serial_helper.serial_data_matching_index != 0:
                scene.serial_helper.serial_data_matching_index = scene.serial_helper.serial_data_matching_index-1
            else:
                scene.serial_helper.serial_data_matching_index = 0
        return {'FINISHED'}


class CopyDriverSerialDataMatchingItemOperator(bpy.types.Operator):
    bl_idname = "serial_data_matching.copy_driver"
    bl_label = "复制驱动器路径到剪贴板"
    index: bpy.props.IntProperty()

    def execute(self, context):
        full_path = f"#bpy.context.scene.serial_helper.serial_data_matching_list[{self.index}].matching_data_value"
        bpy.context.window_manager.clipboard = full_path
        self.report({'INFO'}, f"已复制驱动器路径: {full_path}")
        return {'FINISHED'}


class UpdateSerialDriverDataMatchingOperator(bpy.types.Operator):
    bl_idname = "serial_data_matching.update_driver"
    bl_label = "更新驱动器数据"

    def execute(self, context):
        scene = context.scene
        scene.serial_helper.driver_remove("serial_data_matching_update_use")
        driver = scene.serial_helper.driver_add("serial_data_matching_update_use").driver
        var = driver.variables.new()
        var.name = "serial_data_matching_update_use"
        var.type = "SINGLE_PROP"
        var.targets[0].id_type = "SCENE"
        var.targets[0].id = bpy.context.scene
        var.targets[0].data_path = "serial_helper.serial_data_matching_list[0].matching_data_value"
        driver.expression = f"serial_data_matching_update_use"
        return {'FINISHED'}


def format_replace_var_string(self, input_string):
    scene = bpy.context.scene
    eval_globals = {
        'random': random,
        'math': math,  # 示例：如果使用了 math 模块
        # 可以添加更多你可能需要的模块
    }
    for item in scene.serial_helper.Send_variable_list:
        try:
            value = eval(item.data_path)  # 获取数据路径对应的值
            input_string = input_string.replace(f"{{{item.variable_name}}}", str(value))
        except:
            print(f"变量{item.variable_name}数据路径{item.data_path}获取失败")
            self.report({'ERROR'}, f"变量{item.variable_name}数据路径{item.data_path}获取失败")
    return input_string


class SendDataSerialOperator(bpy.types.Operator):
    bl_idname = "serial.send_data_operator"
    bl_label = "发送数据"

    def execute(self, context):
        scene = context.scene
        SerialConnection = bpy.app.driver_namespace["serial_connection"]
        data_to_send = scene.serial_helper.serial_send_data
        var_replace_str = format_replace_var_string(self, data_to_send)
        print(var_replace_str)
        if scene.serial_helper.is_newline:
            var_replace_str = var_replace_str+"\r\n"
        SerialConnection.serial.write(var_replace_str.encode(scene.serial_helper.Encoding))
        return {'FINISHED'}


class AddSerialHelperSendVariableOperator(bpy.types.Operator):
    bl_idname = "serial.add_variable_operator"
    bl_label = "Add Variable"

    def execute(self, context):
        item = context.scene.serial_helper.Send_variable_list.add()
        item.variable_name = "var_name_" + str(len(context.scene.serial_helper.Send_variable_list))
        item.data_path = "data_path"
        context.scene.serial_helper.Send_variable_index = len(context.scene.serial_helper.Send_variable_list) - 1
        return {'FINISHED'}


class RemoveSerialHelperSendVariableOperator(bpy.types.Operator):
    bl_idname = "serial.remove_variable_operator"
    bl_label = "Remove Variable"

    def execute(self, context):
        variable_list = context.scene.serial_helper.Send_variable_list
        index = context.scene.serial_helper.Send_variable_index
        variable_list.remove(index)
        if index != 0:
            context.scene.serial_helper.Send_variable_index = context.scene.serial_helper.Send_variable_index - 1
        return {'FINISHED'}


class AddSerialFastMessageListOperator(bpy.types.Operator):
    bl_idname = "serial.add_fast_message_operator"
    bl_label = "Add Fast Message"

    def execute(self, context):
        item = context.scene.serial_helper.fast_message_list.add()
        item.message_name = "name_" + str(len(context.scene.serial_helper.fast_message_list))
        item.message = ""
        context.scene.serial_helper.fast_message_index = len(context.scene.serial_helper.fast_message_list) - 1
        return {'FINISHED'}


class RemoveSerialFastMessageListOperator(bpy.types.Operator):
    bl_idname = "serial.remove_fast_message_operator"
    bl_label = "Remove Fast Message"

    def execute(self, context):
        list = context.scene.serial_helper.fast_message_list
        index = context.scene.serial_helper.fast_message_index
        list.remove(index)
        if index != 0:
            context.scene.serial_helper.fast_message_index = context.scene.serial_helper.fast_message_index - 1
        return {'FINISHED'}


class SendFastMessageOperator(bpy.types.Operator):
    bl_idname = "serial.send_fast_message_operator"
    bl_label = "发送快速消息"
    index: bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        message = scene.serial_helper.fast_message_list[self.index].message
        scene.serial_helper.serial_send_data = message
        bpy.ops.serial.send_data_operator()
        return {'FINISHED'}


def send_data_periodically():
    scene = bpy.context.scene
    if scene.serial_helper.is_auto_send:
        bpy.ops.serial.send_data_operator()
        auto_send_interval = scene.serial_helper.auto_send_interval
        return auto_send_interval  # Repeat every second
    else:
        return None  # Stop the timer if sending is disabled


def update_sending_state(self, context):
    # timer_handle = bpy.app.timers.is_registered(send_data_periodically)
    # print(timer_handle)
    if bpy.context.scene.serial_helper.is_auto_send:
        bpy.app.timers.register(send_data_periodically, first_interval=1.0)
    else:
        bpy.app.timers.unregister(send_data_periodically)


class testOperator(bpy.types.Operator):
    bl_idname = "test.operator"
    bl_label = "Test Operator"

    def execute(self, context):
        print(context.scene.serial_helper.bytesize)
        return {'FINISHED'}


class stopReceivingOperator(bpy.types.Operator):
    bl_idname = "serial.stop_receiving_operator"
    bl_label = "暂停接收"
    bl_options = {'REGISTER', 'UNDO'}  # 选项，注册到操作列表中，提供撤销功能

    def execute(self, context):
        bpy.context.scene.serial_helper.StopReceiving = not bpy.context.scene.serial_helper.StopReceiving
        return {'FINISHED'}


class switchTheSerialPortOperator(bpy.types.Operator):
    bl_idname = "serial.switch_operator"  # 操作符 ID
    bl_label = "打开串口"  # 操作符显示名称
    # bl_options = {'REGISTER', 'UNDO'}  # 选项，注册到操作列表中，提供撤销功能

    def execute(self, context):
        # 在这里执行按钮操作
        context.scene.serial_helper.serial_is_open = not context.scene.serial_helper.serial_is_open
        if context.scene.serial_helper.serial_is_open:

            if bpy.context.scene.serial_helper.use_input_serial_port:
                port = bpy.context.scene.serial_helper.user_input_serial_port
            else:
                port = bpy.context.scene.serial_helper.serial_ports
            print(context.scene.serial_helper.serial_is_open)
            print(port)
            print(context.scene.serial_helper.baudrate)
            try:
                open_serial_port()
                self.report(
                    {'INFO'}, f"串口打开{port}")
            except Exception as e:
                print(f"An error occurred: {e}")
                context.scene.serial_helper.serial_is_open = False
                self.report(
                    {'ERROR'}, f"串口打开失败,{e}")

        else:
            if "serial_connection" in bpy.app.driver_namespace:
                serial_thread = bpy.app.driver_namespace["serial_thread"]
                serial_thread.should_terminate = True
                serial_SerialConnection = bpy.app.driver_namespace["serial_connection"]
                serial_SerialConnection.serial.close()

                del bpy.app.driver_namespace["serial_connection"]
                del bpy.app.driver_namespace["serial_thread"]
                print("成功关闭串口")
            else:
                print("无可关闭的串口")
            self.report(
                {'INFO'}, "串口关闭.")

        return {'FINISHED'}


def update_serial_ports(self, context):
    ports = [port.device for port in serial.tools.list_ports.comports()]
    return [(port, port, "") for port in ports]


class SerialHelperProperties(bpy.types.PropertyGroup):
    use_input_serial_port: bpy.props.BoolProperty(
        name="是否手动输入端口",
        description="是否手动输入端口",
        default=False
    )
    serial_ports: bpy.props.EnumProperty(
        name="串口端口",
        description="串口端口",
        items=update_serial_ports,
    )
    user_input_serial_port: bpy.props.StringProperty(
        name="手动端口",
        description="手动输入的端口",
        default="COM3"
    )

    serial_is_open: bpy.props.BoolProperty(
        name="serial_is_open_name",
        description="串口是否打开",
        default=False
    )
    baudrate: bpy.props.IntProperty(
        name="波特率",
        description="波特率",
        default=115200
    )
    # FIVEBITS、SIXBITS、SEVENBITS、EIGHTBITS
    bytesize: bpy.props.EnumProperty(
        name="数据位",
        description="数据位",
        items=[
            ('5', "5位", "使用7位数据位"),
            ('6', "6位", "使用8位数据位"),
            ('7', "7位", "使用7位数据位"),
            ('8', "8位", "使用8位数据位"),
        ],
        default='8'
    )
    # STOPBITS_ONE、STOPBITS_ONE_POINT_FIVE、STOPBITS_TWO
    stopbits: bpy.props.EnumProperty(
        name="停止位",
        description="停止位",
        items=[
            ('1', "1", "1位停止位"),
            ('1.5', "1.5", "1.5位停止位"),
            ('2', "2", "2位停止位"),
            # 有些系统可能还支持其他类型的校验位，如：
            # 'MARK', "标记校验", "标记校验位"),
            # 'SPACE', "空格校验", "空格校验位"),
        ],
        default='1'
    )
    # PARITY_NONE、PARITY_EVEN、PARITY_ODD PARITY_MARK、PARITY_SPACE
    parity: bpy.props.EnumProperty(
        name="校验位",
        description="校验位",
        items=[
            ('N', "NONE", "无校验位"),
            ('E', "偶校验", "偶数校验位"),
            ('O', "奇校验", "奇数校验位"),
            ('M', "MARK", "标记校验位"),
            ('S', "SPACE", "空格校验位"),
        ],
        default='N'
    )
    Encoding: bpy.props.EnumProperty(
        name="编码格式",
        description="编码格式",
        items=[
            ('utf-8', "utf-8", "utf-8"),
            ('ascii', "ascii", "ascii"),
            ('gbk', "gbk", "gbk"),
            ('utf-16', "utf-16", "utf-16"),
            ('gb2312', "gb2312", "gb2312"),
        ],
        default='utf-8'
    )
    StopReceiving: bpy.props.BoolProperty(
        name="StopReceiving",
        description="暂停接收",
        default=False
    )
    serial_data_list: bpy.props.CollectionProperty(type=SerialDataItemProperties)
    serial_data_index: bpy.props.IntProperty()
    serial_data_count: bpy.props.IntProperty(default=1)
    serial_data_max_count: bpy.props.IntProperty(default=5)
    serial_data_matching_list: bpy.props.CollectionProperty(type=SerialDataMatchingProperties)
    serial_data_matching_index: bpy.props.IntProperty()
    serial_data_matching_update_use: bpy.props.FloatProperty(default=0)
    serial_send_data: bpy.props.StringProperty(default="")
    is_newline: bpy.props.BoolProperty(default=True)
    Send_variable_list: bpy.props.CollectionProperty(type=SendVariablePathItem)
    Send_variable_index: bpy.props.IntProperty()
    is_auto_send: bpy.props.BoolProperty(default=False, update=update_sending_state)
    auto_send_interval: bpy.props.FloatProperty(default=1, min=0.01)
    fast_message_list: bpy.props.CollectionProperty(type=SerialFastMessageItem)
    fast_message_index: bpy.props.IntProperty()


property_Class = [
    SerialDataItemProperties,
    SerialDataMatchingProperties,
    SendVariablePathItem,
    SerialFastMessageItem,
    SerialHelperProperties,



]

Panel_Class = [
    SerialHelpPanel,
    ReceivingSettingsPanel,
    SerialDataDisplayPanel,
    SERIAL_UL_DataList,
    SerialHelperDataMatchingPanel,
    SERIAL_UL_DataMatchingList,
    SendDataSerialPanel,
    SERIAL_UL_SendVariable_list,
    SERIAL_UL_FastMessage_list,
    SerialHelperSendVariablePanel,
    SerialFastMessagePanle,
]

Operator_Class = [
    testOperator,
    switchTheSerialPortOperator,
    stopReceivingOperator,
    ClearSerialDataItemsOperator,
    AddSerialDataMatchingItemOperator,
    RemoveSerialDataMatchingItemOperator,
    CopyDriverSerialDataMatchingItemOperator,
    UpdateSerialDriverDataMatchingOperator,
    SendDataSerialOperator,
    AddSerialHelperSendVariableOperator,
    RemoveSerialHelperSendVariableOperator,
    AddSerialFastMessageListOperator,
    RemoveSerialFastMessageListOperator,
    SendFastMessageOperator
]


def register():

    for cls in property_Class:
        bpy.utils.register_class(cls)

    for cls in Panel_Class:
        bpy.utils.register_class(cls)

    for cls in Operator_Class:
        bpy.utils.register_class(cls)

    # 将 serial_helper 属性添加到 Scene 中
    bpy.types.Scene.serial_helper = bpy.props.PointerProperty(type=SerialHelperProperties)


def unregister():

    for cls in property_Class:
        bpy.utils.unregister_class(cls)

    for cls in Panel_Class:
        bpy.utils.unregister_class(cls)

    for cls in Operator_Class:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.serial_helper


if __name__ == "__main__":
    register()
