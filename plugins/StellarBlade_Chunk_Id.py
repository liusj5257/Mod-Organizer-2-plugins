import mobase
import os
import logging
import uuid
import struct
from typing import List, Dict
from enum import IntEnum
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMainWindow, QWidget, QMessageBox
from collections import defaultdict
from dataclasses import dataclass, field
from ctypes import c_uint8, c_uint16, c_uint32, c_uint64


class EIoContainerFlags(IntEnum):
    NONE = 0x00
    COMPRESSED = 0x01
    ENCRYPTED = 0x02
    SIGNED = 0x04
    INDEXED = 0x08


class EIoChunkType(IntEnum):
    INVALID = 0
    INSTALL_MANIFEST = 1
    EXPORT_BUNDLE_DATA = 2
    BULK_DATA = 3
    OPTIONAL_BULK_DATA = 4
    MEMORY_MAPPED_BULK_DATA = 5
    LOADER_GLOBAL_META = 6
    LOADER_INITIAL_LOAD_META = 7
    LOADER_GLOBAL_NAMES = 8
    LOADER_GLOBAL_NAME_HASHES = 9
    CONTAINER_HEADER = 10


@dataclass
class FGuid:
    A: c_uint32 = field(default=c_uint32(0))
    B: c_uint32 = field(default=c_uint32(0))
    C: c_uint32 = field(default=c_uint32(0))
    D: c_uint32 = field(default=c_uint32(0))


@dataclass
class FIoStoreTocHeader:

    magic: bytes = field(default=b"-==--==--==--==-")

    version: c_uint8 = field(default=c_uint8(0))
    reserved0: c_uint8 = field(default=c_uint8(0))
    reserved00: c_uint16 = field(default=c_uint16(0))
    # TOC 结构信息
    TocHeaderSize: c_uint32 = field(default=c_uint32(0))
    TocEntryCount: c_uint32 = field(default=c_uint32(0))
    TocCompressedBlockEntryCount: c_uint32 = field(default=c_uint32(0))
    TocCompressedBlockEntrySize: c_uint32 = field(default=c_uint32(0))
    # 压缩信息
    CompressionMethodNameCount: c_uint32 = field(default=c_uint32(0))
    CompressionMethodNameLength: c_uint32 = field(default=c_uint32(0))
    CompressionBlockSize: c_uint32 = field(default=c_uint32(0))
    # 目录信息
    DirectoryIndexSize: c_uint32 = field(default=c_uint32(0))
    PartitionCount: c_uint32 = field(default=c_uint32(0))

    # 容器标识
    FIoContainerId: c_uint64 = field(default=c_uint64(0))
    EncryptionKeyGuid: FGuid = field(default_factory=FGuid)

    ContainerFlags: c_uint8 = field(default=c_uint8(0))
    # 其他信息
    Reserved1: c_uint8 = field(default=c_uint8(0))
    Reserved2: c_uint16 = field(default=c_uint16(0))

    TocChunkPerfectHashSeedsCount: c_uint32 = field(default=c_uint32(0))
    PartitionSize: c_uint64 = field(default=c_uint64(0))
    TocChunksWithoutPerfectHashCount: c_uint32 = field(default=c_uint32(0))

    Reserved3: c_uint32 = field(default=c_uint32(0))
    Reserved4: c_uint64 = field(default=c_uint64(0))
    Reserved5: c_uint64 = field(default=c_uint64(0))
    Reserved6: c_uint64 = field(default=c_uint64(0))
    Reserved7: c_uint64 = field(default=c_uint64(0))
    Reserved8: c_uint64 = field(default=c_uint64(0))

    def __post_init__(self):
        # 验证 magic 长度
        if len(self.magic) != 16:
            raise ValueError(f"magic must be 16 bytes, got {len(self.magic)} bytes")

        # 自动转换整数到 ctypes 类型
        if isinstance(self.version, int):
            self.version = c_uint8(self.version)
        if isinstance(self.FIoContainerId, int):
            self.FIoContainerId = c_uint64(self.FIoContainerId)


class UTOCParser:
    EXPECTED_MAGIC = b"-==--==--==--==-"

    def __init__(self, logger):
        self._logger = logger
        self.parsed_data = defaultdict(list)

        self._uint40_fmt = struct.Struct("<5B")
        self._uint24_fmt = struct.Struct("<3B")

        self.reset_parser_state()
        self.all_header = None
        self.container_ids = []
        self.chunk_ids = []
        self.Force = False

    def reset_parser_state(self):
        """重置解析器状态，为解析新文件做准备"""
        self.header = None
        self.offset_lengths = []
        self.compressed_blocks = []
        self.directory_index = b""
        self.entry_metas = []
        self.file_size = 0

    def generate_u64_id(self, ids: List[c_uint64]) -> c_uint64:
        """生成一个新的64位无符号整数ID"""
        for _ in range(10):
            candidate = uuid.uuid4().int & 0xFFFFFFFFFFFFFFFF
            if candidate not in ids:
                ids.append(c_uint64(candidate))
                return c_uint64(candidate)
        raise ValueError("无法生成唯一的64位无符号整数ID")

    def parse_utoc(self, utoc_file: str):
        """解析单个utoc文件"""
        self.reset_parser_state()
        base_name = os.path.basename(utoc_file)
        ucas_file = utoc_file.replace(".utoc", ".ucas")
        if base_name.endswith(".utoc"):
            self._logger.debug(f"开始解析文件: {base_name}")
        # try:
            with open(utoc_file, "r+b") as utoc_f:
                file_data = utoc_f.read()
                self.file_size = len(file_data)

                # 解析header
                changed_contaniner_id = self._parse_header(file_data)
                # 解析 ids
                found = False
                index = 0
                newContainerId = 0
                if changed_contaniner_id or self.Force:
                    newContainerId = self.generate_u64_id(self.container_ids).value
                    utoc_f.seek(56)
                    utoc_f.write(struct.pack("<Q", newContainerId))
                    for index in range(self.header["TocEntryCount"]):
                        id, reverse1, reverse2, idtype = struct.unpack(
                            "<QHBB",
                            file_data[144 + index * 12 : 144 + (index + 1) * 12],
                        )
                        self._logger.debug(f"{id,idtype,index,self.header["FIoContainerId"]}")
                        if id == self.header["FIoContainerId"]:
                            if not idtype == 10:
                                self._logger.error(
                                    f"container_id类型不符合{base_name}"
                                )
                            utoc_f.seek(144 + index * 12)
                            utoc_f.write(struct.pack("<Q", newContainerId))
                            found = True
                            break
                    if not found:
                        self._logger.error(f"未找到container_id{base_name}")

                    changed_ids = None
                    # 获取对应的offset  length
                    DataOffset = 144 + self.header["TocEntryCount"] * 12 + index * 10
                    self._logger.debug(f"index= {index} DataOffset = {DataOffset}")
                    offset_bytes = file_data[DataOffset : DataOffset + 5]
                    length_bytes = file_data[DataOffset + 5 : DataOffset + 10]

                    offset = int.from_bytes(offset_bytes, byteorder="big")
                    length = int.from_bytes(length_bytes, byteorder="big")
                    self._logger.debug(f"offset = {hex(offset)},length = {hex(length)}")

                    # 计算CompressedBlock的index
                    CompressionBlockSize = self.header["CompressionBlockSize"]
                    FirstBlockIndex = offset // CompressionBlockSize
                    LastBlockIndex = (
                        offset + length + CompressionBlockSize - 1
                    ) // CompressionBlockSize - 1

                    self._logger.debug(
                        f"FirstBlockIndex {FirstBlockIndex},LastBlockIndex {LastBlockIndex}"
                    )
                    # 获取对应的CompressedBlock
                    DataOffset = (
                        144
                        + self.header["TocEntryCount"] * 12
                        + self.header["TocEntryCount"] * 10
                        + FirstBlockIndex * 12
                    )
                    offset_bytes = file_data[DataOffset : DataOffset + 5]
                    size_bytes = file_data[DataOffset + 5 : DataOffset + 5 + 3]
                    uncompressed_size_bytes = file_data[
                        DataOffset + 5 + 3 : DataOffset + 5 + 3 + 3
                    ]
                    compresseion_method_size_bytes = file_data[
                        DataOffset + 5 + 3 + 3 : DataOffset + 5 + 3 + 3 + 1
                    ]
                    offset = int.from_bytes(offset_bytes, byteorder="little")
                    size = int.from_bytes(size_bytes, byteorder="little")
                    self._logger.debug(f"ucas offset={offset}, size ={size} ")

                    with open(ucas_file, "r+b") as ucas_f:
                        ucas_f.seek(offset)
                        ucas_f.write(struct.pack("<Q", newContainerId))
                        ucas_f.close()
                        self._logger.debug(f"更新ucas容器ID: {newContainerId}")

            #     changed_ids = self._parse_chunk_ids(file_data[144:], utoc_f)
            #     self._logger.debug(f"changed_ids\n {changed_ids} ")
            #     if changed_ids:
            #         self._logger.debug(f"需要替换 {len(changed_ids)} 个ChunkID")
            #         with open(ucas_file, "r+b") as ucas_f:
            #             ucas_data = ucas_f.read()
            #             PackageIds_num = struct.unpack("<I", ucas_data[offset+28:offset+32])[0]
            #             for i in range(PackageIds_num):
            #                 offset2 =offset+ 32 + i * 8
            #                 PackageId = struct.unpack(
            #                     "<Q", ucas_data[offset2 : offset2 + 8]
            #                 )[0]
            #                 new_id = changed_ids[PackageId]
            #                 ucas_f.seek(offset2)
            #                 ucas_f.write(struct.pack("<Q", new_id))
            #                 self._logger.debug(f"ucas : {PackageId} -> {new_id}")

            #             ucas_f.close()
                utoc_f.close()
            self._logger.debug(f"container_ids\n{self.container_ids}")
            if   changed_contaniner_id or self.Force:
                self._logger.debug(f"处理完成: {base_name}")
                return True
            else:
                self._logger.debug(f"无需处理: {base_name}")
                return False

            # except Exception as e:
            #     self._logger.error(f"解析失败: {base_name} - {str(e)}")
            #     return False

    def _parse_chunk_ids(self, data, file) -> Dict[int, int]:
        """解析utoc文件中的chunk ids"""
        id_mapping: Dict[int, int] = {}
        added_ids = set()
        PackageId_format = "<QHBB"
        PackageId_size = struct.calcsize(PackageId_format)

        for i in range(self.header["TocEntryCount"] ):
            PackageId = struct.unpack(PackageId_format, data[:PackageId_size])
            ChunkId = PackageId[0]
            ChunkType = PackageId[3]
            data = data[PackageId_size:]
            # 不需要修改的情况
            if ChunkId not in self.chunk_ids and not self.Force:
                if ChunkId not in added_ids:
                    self.chunk_ids.append(ChunkId)
                    added_ids.add(ChunkId)
                    self._logger.debug(f"记录全新ChunkId: {ChunkId}")
            # 需要修改的情况
            if ChunkId not in added_ids and not ChunkType == 10:
                # 检查是否已有映射关系
                if ChunkId in id_mapping:
                    new_ChunkId = id_mapping[ChunkId]
                    self._logger.debug(f"使用现有映射: {ChunkId} -> {new_ChunkId}")
                else:
                    # 生成新ID并记录映射
                    new_ChunkId = self.generate_u64_id(self.chunk_ids).value
                    id_mapping[ChunkId] = new_ChunkId
                    self._logger.debug(f"生成新ID映射: {ChunkId} -> {new_ChunkId}")

                # 更新文件
                file.seek(144 + i * PackageId_size)
                file.write(struct.pack("<Q", new_ChunkId))
            else:
                self._logger.debug("文件携带多个不同type的相同id，无需处理跳过")

        return id_mapping

    def _parse_header(self, data):
        """解析utoc文件头"""
        header_format = "<16s BBH 9I Q 4I BBH I Q I I 5Q"
        header_size = struct.calcsize(header_format)
        header_data = struct.unpack(header_format, data[:header_size])
        encryption_guid = FGuid(
            A=c_uint32(header_data[14]),
            B=c_uint32(header_data[15]),
            C=c_uint32(header_data[16]),
            D=c_uint32(header_data[17]),
        )
        self.header = {
            "magic": header_data[0],  # 16s
            "version": header_data[1],  # B
            "reserved0": header_data[2],  # B
            "reserved00": header_data[3],  # H
            "TocHeaderSize": header_data[4],  # I
            "TocEntryCount": header_data[5],
            "TocCompressedBlockEntryCount": header_data[6],
            "TocCompressedBlockEntrySize": header_data[7],
            "CompressionMethodNameCount": header_data[8],
            "CompressionMethodNameLength": header_data[9],
            "CompressionBlockSize": header_data[10],
            "DirectoryIndexSize": header_data[11],
            "PartitionCount": header_data[12],
            "FIoContainerId": header_data[13],  # Q
            "EncryptionKeyGuid": encryption_guid,  # 4I
            "ContainerFlags": header_data[18],  # B
            "Reserved1": header_data[19],  # B
            "Reserved2": header_data[20],  # Q
            "TocChunkPerfectHashSeedsCount": header_data[21],  # I
            "PartitionSize": header_data[22],  # Q
            "TocChunksWithoutPerfectHashCount": header_data[23],  # I
            "Reserved3": header_data[24],  # I
            "Reserved4": header_data[25],  # Q
            "Reserved5": header_data[26],
            "Reserved6": header_data[27],
            "Reserved7": header_data[28],
            "Reserved8": header_data[29],
        }

        # 验证魔数
        if self.header["magic"] != self.EXPECTED_MAGIC:
            raise ValueError(
                f"无效的魔数: {self.header.magic.hex()}, 期望: {self.EXPECTED_MAGIC.hex()}"
            )
        # 如果不存在则记录
        if self.header["FIoContainerId"] in self.container_ids:
            return True
        else:
            self.container_ids.append(self.header["FIoContainerId"])
            return False


class StellarBlade_Chunk_Id_Patcher(mobase.IPluginTool):
    _organizer: mobase.IOrganizer
    _mainWindow: QMainWindow
    _parentWidget: QWidget

    def __init__(self):
        super().__init__()
        self._init_logger()
        self.ucas_files = []
        self.num = 0

    def _init_logger(self) -> None:
        """初始化日志记录器"""
        self._logger = logging.getLogger("StellarBlade_Chunk_Id_Patcher")
        self._logger.setLevel(logging.DEBUG)

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        return True

    def name(self) -> str:
        return "StellarBlade_Chunk_Id_Patcher"

    def author(self) -> str:
        return "aqeqqq"

    def description(self) -> str:
        return "StellarBlade_Chunk_Id_Patcher"

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(1, 0, 0, mobase.ReleaseType.BETA)

    def isActive(self) -> bool:
        return self._organizer.pluginSetting(self.name(), "enabled") is True

    def settings(self) -> List[mobase.PluginSetting]:
        return [mobase.PluginSetting("enabled", "enable this plugin", True)]

    def displayName(self) -> str:
        return "StellarBlade_Chunk_Id_Patcher"

    def tooltip(self) -> str:
        return "."

    def icon(self) -> QIcon:
        return QIcon()

    def setParentWidget(self, widget: QWidget):
        self._parentWidget = widget

    def _get_mod_paths(self):
        """获取关键路径信息"""
        self.mod_parent = self._organizer.modsPath()
        self._IPluginGame = self._organizer.managedGame()
        if self._IPluginGame is None:
            self._logger.error("未找到托管游戏! 插件无法初始化。")
            return False
        self.game_path = self._IPluginGame.gameDirectory().path()

    def _collect_UcasFiles(self, entry: mobase.IFileTree):
        """收集所有Ucas文件"""
        for file in list(entry):
            if file.hasSuffix("utoc"):
                baseName = file.name().rsplit(".", 1)[0]
                allMods = self._organizer.modList().allModsByProfilePriority()
                for mod in reversed(allMods):
                    mod_state = self._organizer.modList().state(mod)
                    if mod_state & mobase.ModState.ACTIVE:
                        mod_dir = os.path.join(self.mod_parent, mod)
                        utoc_path = os.path.join(
                            mod_dir, "SB/Content/Paks/~mods/" + baseName + ".utoc"
                        )
                        # ucas_path = os.path.join(
                        #     mod_dir, "SB/Content/Paks/~mods/" + baseName + ".ucas"
                        # )
                        if os.path.exists(utoc_path):
                            self.ucas_files.append(utoc_path)

                        # if os.path.exists(ucas_path):
                        #     self.ucas_files.append(ucas_path)
        self._logger.debug(f"找到 {len(self.ucas_files)} 个 utoc")

    def deprase_utoc(self, ucas_files: list):
        """解析utoc文件"""
        parser = UTOCParser(self._logger)
        for file in ucas_files:
            if parser.parse_utoc(file):
                self.num = self.num + 1

    def display(self):
        """主显示逻辑"""
        self._get_mod_paths()
        virtualFileTree = self._organizer.virtualFileTree()
        mods = virtualFileTree.find("/SB/Content/Paks/~mods")
        if mods is None:
            self._logger.error("在文件树中找不到mods")
            return False

        self._collect_UcasFiles(mods)
        # 解析utoc文件
        self.deprase_utoc(self.ucas_files)
        QMessageBox.information(
            self._parentWidget,
            "处理完成",
            f"总共{len(self.ucas_files)}个utoc\n已处理{self.num}个文件",
        )
        self.num = 0
        self.ucas_files.clear()


def createPlugin() -> mobase.IPlugin:
    return StellarBlade_Chunk_Id_Patcher()
