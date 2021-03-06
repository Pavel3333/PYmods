# -*- coding: utf-8 -*-
import BigWorld
import Keys
import Math
import ResMgr
import glob
import os
import traceback
from PYmodsCore import PYmodsConfigInterface, refreshCurrentVehicle, checkKeys, loadJson, remDups
from collections import OrderedDict
from gui import InputHandler, SystemMessages
from gui.Scaleform.framework import ScopeTemplates, ViewSettings, ViewTypes, g_entitiesFactories
from gui.Scaleform.framework.entities.abstract.AbstractWindowView import AbstractWindowView
from gui.Scaleform.framework.managers.loaders import SFViewLoadParams
from gui.app_loader import g_appLoader
from helpers import dependency
from items.components import component_constants
from items.components.chassis_components import SplineConfig
from items.components.shared_components import EmblemSlot
from items.vehicles import g_cache
from skeletons.gui.shared.utils import IHangarSpace
from vehicle_systems.tankStructure import TankPartNames
from . import __date__, __modID__


def readAODecals(confList):
    retVal = []
    for subDict in confList:
        m = Math.Matrix()
        for strNum, matStr in enumerate(sorted(subDict['transform'].keys())):
            for colNum, elemNum in enumerate(subDict['transform'][matStr]):
                m.setElement(strNum, colNum, elemNum)
        retVal.append(m)

    return retVal


def readEmblemSlots(confList):
    slots = []
    for confDict in confList:
        if confDict['type'] not in component_constants.ALLOWED_EMBLEM_SLOTS:
            print g_config.ID + ': not supported emblem slot type:', confDict['type'] + ', expected:', ' '.join(
                component_constants.ALLOWED_EMBLEM_SLOTS)
        descr = EmblemSlot(Math.Vector3(tuple(confDict['rayStart'])), Math.Vector3(tuple(confDict['rayEnd'])),
                           Math.Vector3(tuple(confDict['rayUp'])), confDict['size'],
                           confDict.get('hideIfDamaged', False), confDict['type'], confDict.get('isMirrored', False),
                           confDict.get('isUVProportional', True), confDict.get('emblemId', None))
        slots.append(descr)

    return slots


class ModelDescriptor(object):
    def __init__(self):
        self.name = ''
        self.authorMessage = ''
        self.whitelists = {'player': set(), 'ally': set(), 'enemy': set()}
        self.data = {
            'chassis': {'undamaged': '', 'AODecals': None, 'hullPosition': None,
                        'wwsound': '', 'wwsoundPC': '', 'wwsoundNPC': ''},
            'hull': {'undamaged': '', 'emblemSlots': [], 'exhaust': {'nodes': [], 'pixie': ''},
                     'camouflage': {'exclusionMask': '', 'tiling': (1.0, 1.0, 0.0, 0.0)}},
            'turret': {'undamaged': '', 'emblemSlots': [],
                       'camouflage': {'exclusionMask': '', 'tiling': (1.0, 1.0, 0.0, 0.0)}},
            'gun': {'undamaged': '', 'emblemSlots': [], 'effects': '', 'reloadEffect': '',
                    'camouflage': {'exclusionMask': '', 'tiling': (1.0, 1.0, 0.0, 0.0)}},
            'engine': {'wwsound': '', 'wwsoundPC': '', 'wwsoundNPC': ''},
            'common': {'camouflage': {'exclusionMask': '', 'tiling': (1.0, 1.0, 0.0, 0.0)}}}


class ConfigInterface(PYmodsConfigInterface):
    hangarSpace = dependency.descriptor(IHangarSpace)

    def __init__(self):
        self.possibleModes = ['player', 'ally', 'enemy', 'remod']
        self.defaultSkinConfig = {'static': {'enabled': True, 'swapPlayer': True, 'swapAlly': True, 'swapEnemy': True},
                                  'dynamic': {'enabled': True, 'swapPlayer': False, 'swapAlly': True, 'swapEnemy': True}}
        self.defaultRemodConfig = {'enabled': True, 'swapPlayer': True, 'swapAlly': True, 'swapEnemy': True}
        self.settings = {'remods': {}, 'skins': {}, 'skins_dynamic': {}}
        self.skinsCache = {'CRC32': '', 'version': ''}
        self.modelsData = {'enabled': True, 'models': {}, 'selected': {'player': {}, 'ally': {}, 'enemy': {}, 'remod': ''}}
        self.skinsData = {
            'enabled': True, 'found': False, 'models': {'static': {}, 'dynamic': {}},
            'priorities': {skinType: {'player': [], 'ally': [], 'enemy': []} for skinType in ('static', 'dynamic')}}
        self.loadingProxy = None
        self.isModAdded = False
        self.collisionEnabled = False
        self.collisionComparisonEnabled = False
        self.dynamicSkinEnabled = False
        self.isInHangar = False
        self.currentMode = self.possibleModes[0]
        super(ConfigInterface, self).__init__()

    def init(self):
        self.ID = __modID__
        self.version = '3.0.0 (%s)' % __date__
        self.author += ' (thx to atacms)'
        self.defaultKeys = {'DynamicSkinHotkey': [Keys.KEY_F1, [Keys.KEY_LCONTROL, Keys.KEY_RCONTROL]],
                            'ChangeViewHotkey': [Keys.KEY_F2, [Keys.KEY_LCONTROL, Keys.KEY_RCONTROL]],
                            'SwitchRemodHotkey': [Keys.KEY_F3, [Keys.KEY_LCONTROL, Keys.KEY_RCONTROL]],
                            'CollisionHotkey': [Keys.KEY_F4, [Keys.KEY_LCONTROL, Keys.KEY_RCONTROL]]}
        self.data = {'enabled': True,
                     'isDebug': True,
                     'DynamicSkinHotkey': self.defaultKeys['DynamicSkinHotkey'],
                     'ChangeViewHotkey': self.defaultKeys['ChangeViewHotkey'],
                     'CollisionHotkey': self.defaultKeys['CollisionHotkey'],
                     'SwitchRemodHotkey': self.defaultKeys['SwitchRemodHotkey'],
                     'remod': True}
        self.i18n = {
            'UI_description': 'Remod Enabler',
            'UI_flash_header': 'Remods and skins setup',
            'UI_flash_header_tooltip': "Extended setup for RemodEnabler by "
                                       "<font color='#DD7700'><b>Polyacov_Yury</b></font>",
            'UI_flash_remodSetupBtn': 'Remods setup',
            'UI_flash_remodWLBtn': 'Remod whitelists',
            'UI_flash_remodCreateBtn': 'Create remod',
            'UI_flash_remodCreate_name_text': 'Remod name',
            'UI_flash_remodCreate_name_tooltip': 'Remod unique ID and config file name.',
            'UI_flash_remodCreate_message_text': 'Author message',
            'UI_flash_remodCreate_message_tooltip': 'This message is displayed in hangar every time the remod is selected.'
                                                    '\nLeave blank if not required.',
            'UI_flash_remodCreate_name_empty': '<b>Remod creation failed:</b>\nname is empty.',
            'UI_flash_remodCreate_error': '<b>Remod creation failed:</b>\ncheck python.log for additional information.',
            'UI_flash_remodCreate_success': '<b>Remod created successfully</b>.',
            'UI_flash_skinSetupBtn': 'Skins setup',
            'UI_flash_skinPriorityBtn': 'Skin priorities',
            'UI_flash_skinType_static': 'Static',
            'UI_flash_skinType_dynamic': 'Dynamic',
            'UI_flash_team_player': 'Player',
            'UI_flash_team_ally': 'Ally',
            'UI_flash_team_enemy': 'Enemy',
            'UI_flash_whiteList_addBtn': 'Add',
            'UI_flash_whiteList_header_text': 'Whitelists for:',
            'UI_flash_whiteList_header_tooltip': 'Open to view all items, select an item to delete.\n\n'
                                                 'List is scrollable if longer than 10 items.',
            'UI_flash_whiteDropdown_default': 'Expand',
            'UI_flash_useFor_header_text': 'Use this item for:',
            'UI_flash_useFor_enable_text': 'Enabled',
            'UI_flash_useFor_player_text': 'Player',
            'UI_flash_useFor_ally_text': 'Allies',
            'UI_flash_useFor_enemy_text': 'Enemies',
            'UI_flash_WLVehDelete_header': 'Confirmation',
            'UI_flash_WLVehDelete_text': 'Are you sure you want to delete this vehicle from this whitelist?',
            'UI_flash_vehicleDelete_success': 'Vehicle deleted from whitelist: ',
            'UI_flash_vehicleAdd_success': 'Vehicle added to whitelist: ',
            'UI_flash_vehicleAdd_dupe': 'Vehicle already in whitelist: ',
            'UI_flash_vehicleAdd_notSupported': 'Vehicle is not supported by RemodEnabler.',
            'UI_flash_backBtn': 'Back',
            'UI_flash_saveBtn': 'Save',
            'UI_loading_autoLogin': 'Log in afterwards',
            'UI_loading_autoLogin_cancel': 'Cancel auto login',
            'UI_loading_done': ' Done!',
            'UI_loading_header_CRC32': 'RemodEnabler: checking textures',
            'UI_loading_header_models_clean': 'RemodEnabler: cleaning models',
            'UI_loading_header_models_unpack': 'RemodEnabler: unpacking models',
            'UI_loading_package': 'Unpacking %s:',
            'UI_loading_skinPack': 'Checking %s:',
            'UI_loading_skinPack_clean': 'Cleaning %s:',
            'UI_loading_skins': 'Checking skins...',
            'UI_loading_skins_clean': 'Cleaning skin models...',
            'UI_restart_header': 'RemodEnabler: restart',
            'UI_restart_text': (
                'Skin models have been re-unpacked. Client restart required to accept changes.\n'
                'Client proper behaviour <b>NOT GUARANTEED</b> until next client start. This will <b>not</b>'
                'be required later. Do you want to restart the game now?'),
            'UI_restart_button_restart': 'Restart',
            'UI_restart_button_shutdown': 'Shutdown',
            'UI_setting_isDebug_text': 'Enable extended log printing',
            'UI_setting_isDebug_tooltip': 'If enabled, your python.log will be harassed with mod\'s debug information.',
            'UI_setting_remod_text': 'Enable all remods preview mode',
            'UI_setting_remod_tooltip': 'If disabled, all remods preview mode will not be active.',
            'UI_setting_ChangeViewHotkey_text': 'View mode switch hotkey',
            'UI_setting_ChangeViewHotkey_tooltip': (
                'This hotkey will switch the preview mode in hangar.\n<b>Possible modes:</b>\n'
                ' • Player tank\n • Ally tank\n • Enemy tank%(remod)s'),
            'UI_setting_ChangeViewHotkey_remod': '\n • Remod preview',
            'UI_setting_DynamicSkinHotkey_text': 'Dynamic skin display switch hotkey',
            'UI_setting_DynamicSkinHotkey_tooltip': (
                'This hotkey will switch dynamic skin preview mode in hangar.\n'
                '<b>Possible modes:</b>\n • OFF\n • Model add'),
            'UI_setting_CollisionHotkey_text': 'Collision view switch hotkey',
            'UI_setting_CollisionHotkey_tooltip': (
                'This hotkey will switch collision preview mode in hangar.\n'
                '<b>Possible modes:</b>\n • OFF\n • Model replace\n • Model add'),
            'UI_setting_SwitchRemodHotkey_text': 'Remod switch hotkey',
            'UI_setting_SwitchRemodHotkey_tooltip': (
                'This hotkey will cycle through all remods (ignoring whitelists in remod preview mode).'),
            'UI_disableCollisionComparison': '<b>RemodEnabler:</b>\nDisabling collision comparison mode.',
            'UI_enableCollisionComparison': '<b>RemodEnabler:</b>\nEnabling collision comparison mode.',
            'UI_enableCollision': '<b>RemodEnabler:</b>\nEnabling collision mode.',
            'UI_enableDynamicSkin': '<b>RemodEnabler:</b>\nEnabling dynamic skins display.',
            'UI_disableDynamicSkin': '<b>RemodEnabler:</b>\nDisabling dynamic skins display.',
            'UI_install_skin': '<b>RemodEnabler:</b>\nSkin installed: ',
            'UI_install_skin_dynamic': '<b>RemodEnabler:</b>\nDynamic skin installed: ',
            'UI_install_remod': '<b>RemodEnabler:</b>\nRemod installed: ',
            'UI_install_default': '<b>RemodEnabler:</b>\nDefault model applied.',
            'UI_mode': '<b>RemodEnabler:</b>\nCurrent display mode: ',
            'UI_mode_player': 'player tank preview',
            'UI_mode_ally': 'ally tank preview',
            'UI_mode_enemy': 'enemy tank preview',
            'UI_mode_remod': 'all remods preview'}
        super(ConfigInterface, self).init()

    def createTemplate(self):
        viewKey = self.tb.createHotKey('ChangeViewHotkey')
        viewKey['tooltip'] %= {'remod': self.i18n['UI_setting_ChangeViewHotkey_remod'] if self.data['remod'] else ''}
        template = {'modDisplayName': self.i18n['UI_description'],
                    'settingsVersion': 200,
                    'enabled': self.data['enabled'],
                    'column1': [self.tb.createHotKey('DynamicSkinHotkey'),
                                self.tb.createControl('isDebug'),
                                self.tb.createControl('remod')],
                    'column2': [viewKey,
                                self.tb.createHotKey('SwitchRemodHotkey'),
                                self.tb.createHotKey('CollisionHotkey')]}
        return template

    def onMSADestroy(self):
        refreshCurrentVehicle()

    def onApplySettings(self, settings):
        super(ConfigInterface, self).onApplySettings(settings)
        if self.isModAdded:
            kwargs = dict(id='RemodEnablerUI', enabled=self.data['enabled'])
            try:
                BigWorld.g_modsListApi.updateModification(**kwargs)
            except AttributeError:
                BigWorld.g_modsListApi.updateMod(**kwargs)

    def readCurrentSettings(self, quiet=True):
        super(ConfigInterface, self).readCurrentSettings()
        self.settings = loadJson(self.ID, 'settings', self.settings, self.configPath)
        self.skinsCache.update(loadJson(self.ID, 'skinsCache', self.skinsCache, self.configPath))
        configsPath = self.configPath + 'remods/*.json'
        self.modelsData['enabled'] = bool(glob.glob(configsPath))
        if self.modelsData['enabled']:
            self.modelsData['selected'] = selectedData = loadJson(
                self.ID, 'remodsCache', self.modelsData['selected'], self.configPath)
            for key in selectedData.keys():
                if not key.islower():
                    selectedData[key.lower()] = selectedData.pop(key)
            snameList = set()
            for configPath in glob.iglob(configsPath):
                sname = os.path.basename(configPath).split('.')[0]
                confDict = loadJson(self.ID, sname, {}, os.path.dirname(configPath) + '/', encrypted=True)
                if not confDict:
                    print self.ID + ': error while reading', os.path.basename(configPath) + '.'
                    continue
                settingsDict = self.settings['remods'].setdefault(sname, {})
                snameList.add(sname)
                if not settingsDict.setdefault('enabled', self.defaultRemodConfig['enabled']):
                    print self.ID + ':', sname, 'disabled, moving on'
                    if sname in self.modelsData['models']:
                        del self.modelsData['models'][sname]
                    continue
                self.modelsData['models'][sname] = pRecord = ModelDescriptor()
                pRecord.name = sname
                pRecord.authorMessage = confDict.get('authorMessage', '')
                for tankType in ('player', 'ally', 'enemy'):
                    selected = selectedData[tankType]
                    swapKey = 'swap' + tankType.capitalize()
                    WLKey = tankType + 'Whitelist'
                    whiteStr = settingsDict.setdefault(WLKey, confDict.get(WLKey, ''))
                    templist = [x.strip() for x in whiteStr.split(',') if x]
                    whitelist = pRecord.whitelists[tankType]
                    whitelist.update(templist)
                    if not whitelist:
                        if self.data['isDebug']:
                            print self.ID + ': empty whitelist for', sname + '. Not applied to', tankType, 'tanks.'
                    else:
                        if self.data['isDebug']:
                            print self.ID + ': whitelist for', tankType + ':', list(whitelist)
                        for xmlName in selected:
                            if sname == selected[xmlName] and xmlName not in whitelist:
                                selected[xmlName] = None
                    if not settingsDict.setdefault(swapKey, confDict.get(swapKey, self.defaultRemodConfig[swapKey])):
                        if self.data['isDebug']:
                            print self.ID + ':', tankType, 'swapping in', sname, 'disabled.'
                        whitelist.clear()
                        for xmlName in selected:
                            if sname == selected[xmlName]:
                                selected[xmlName] = None
                for key, data in pRecord.data.iteritems():
                    if key == 'common':
                        confSubDict = confDict
                    else:
                        confSubDict = confDict.get(key)
                    if not confSubDict:
                        continue
                    if 'undamaged' in data:
                        data['undamaged'] = confSubDict['undamaged']
                    if 'AODecals' in data and 'AODecals' in confSubDict and 'hullPosition' in confSubDict:
                        data['AODecals'] = readAODecals(confSubDict['AODecals'])
                        data['hullPosition'] = Math.Vector3(tuple(confSubDict['hullPosition']))
                    if 'camouflage' in data and 'exclusionMask' in confSubDict.get('camouflage', {}):
                        data['camouflage']['exclusionMask'] = confSubDict['camouflage']['exclusionMask']
                        if 'tiling' in confSubDict['camouflage']:
                            data['camouflage']['tiling'] = tuple(confDict['camouflage']['tiling'])
                    elif key == 'common' and self.data['isDebug']:
                        print self.ID + ': default camomask not found for', sname
                    if 'emblemSlots' in data:
                        data['emblemSlots'] = readEmblemSlots(confSubDict.get('emblemSlots', []))
                    if 'exhaust' in data:
                        if 'nodes' in confSubDict.get('exhaust', {}):
                            data['exhaust']['nodes'] = confSubDict['exhaust']['nodes'].split()
                        if 'pixie' in confSubDict.get('exhaust', {}):
                            data['exhaust']['pixie'] = confSubDict['exhaust']['pixie']
                    if key == 'chassis':
                        for k in ('traces', 'tracks', 'wheels', 'groundNodes', 'trackNodes', 'splineDesc', 'trackParams'):
                            data[k] = confSubDict[k]
                    for subKey in ('effects', 'reloadEffect', 'wwsoundPC', 'wwsoundNPC'):
                        if subKey in data and subKey in confSubDict:
                            data[subKey] = confSubDict[subKey]
                if self.data['isDebug']:
                    print self.ID + ': config for', sname, 'loaded.'

            for sname in self.modelsData['models'].keys():
                if sname not in snameList:
                    del self.modelsData['models'][sname]

            for sname in self.settings['remods'].keys():
                if sname not in snameList:
                    del self.settings['remods'][sname]

            if not self.modelsData['models']:
                if not quiet:
                    print self.ID + ': no configs found, model module standing down.'
                self.modelsData['enabled'] = False
                loadJson(self.ID, 'remodsCache', selectedData, self.configPath, True, quiet=quiet)
            else:
                remodTanks = {key: set() for key in selectedData}
                for modelDesc in self.modelsData['models'].values():
                    for tankType, whitelist in modelDesc.whitelists.iteritems():
                        for xmlName in whitelist:
                            remodTanks[tankType].add(xmlName)
                            if xmlName not in selectedData[tankType]:
                                selectedData[tankType][xmlName] = None
                for tankType in ('player', 'ally', 'enemy'):
                    for xmlName in selectedData[tankType].keys():
                        if (selectedData[tankType][xmlName] and selectedData[tankType][
                            xmlName] not in self.modelsData['models']):
                            selectedData[tankType][xmlName] = None
                        if xmlName not in remodTanks[tankType]:
                            del selectedData[tankType][xmlName]
                if selectedData['remod'] and selectedData['remod'] not in self.modelsData['models']:
                    selectedData['remod'] = ''
                loadJson(self.ID, 'remodsCache', selectedData, self.configPath, True, quiet=quiet)
        else:
            if not quiet:
                print self.ID + ': no remods found, model module standing down.'
            self.modelsData['enabled'] = False
            loadJson(self.ID, 'remodsCache', self.modelsData['selected'], self.configPath, True, quiet=quiet)
        self.skinsData['enabled'] = ResMgr.openSection('vehicles/skins/') is not None and ResMgr.isDir('vehicles/skins/')
        if self.skinsData['enabled']:
            self.skinsData['priorities'] = loadJson(self.ID, 'skinsPriority', self.skinsData['priorities'], self.configPath)
            skinDir = 'vehicles/skins/textures/'
            for skinTypeSuff in ('', '_dynamic'):
                skinType = 'static' if not skinTypeSuff else skinTypeSuff[1:]
                for key in self.skinsData['priorities'][skinType].keys():
                    if not key.islower():
                        self.skinsData['priorities'][skinType][key.lower()] = self.skinsData['priorities'][skinType].pop(key)
                skinsSettings = self.settings['skins' + skinTypeSuff]
                disabledSkins = []
                if self.data['isDebug']:
                    print self.ID + ': loading configs for', skinType, 'skins'
                skinDirSect = ResMgr.openSection(skinDir)
                for sname in [] if skinDirSect is None else remDups(skinDirSect.keys()):
                    confDict = skinsSettings.setdefault(sname, self.defaultSkinConfig[skinType])
                    if not confDict.get('enabled', True):
                        print self.ID + ':', sname, 'disabled, moving on'
                        disabledSkins.append(sname)
                        continue
                    self.skinsData['models'][skinType][sname] = pRecord = {'name': '', 'whitelist': set()}
                    pRecord['name'] = sname
                    priorities = self.skinsData['priorities'][skinType]
                    for tankType in priorities:
                        key = 'swap' + tankType.capitalize()
                        if not confDict.setdefault(key, self.defaultSkinConfig[skinType][key]):
                            if self.data['isDebug']:
                                print self.ID + ':', tankType, 'swapping in', sname, 'disabled.'
                            if sname in priorities[tankType]:
                                priorities[tankType].remove(sname)
                            continue
                        if sname not in priorities[tankType]:
                            priorities[tankType].append(sname)
                    pRecord['whitelist'].clear()
                    vehiclesDirPath = skinDir + sname + '/vehicles/'
                    vehiclesDirSect = ResMgr.openSection(vehiclesDirPath)
                    for curNation in [] if vehiclesDirSect is None else remDups(vehiclesDirSect.keys()):
                        nationDirPath = vehiclesDirPath + curNation + '/'
                        nationDirSect = ResMgr.openSection(nationDirPath)
                        for vehicleName in [] if nationDirSect is None else remDups(nationDirSect.keys()):
                            vehDirPath = nationDirPath + vehicleName + '/'
                            vehDirSect = ResMgr.openSection(vehDirPath)
                            tracksDirPath = vehDirPath + 'tracks/'
                            tracksDirSect = ResMgr.openSection(tracksDirPath)
                            if not any(texName.endswith('.dds') for texName in (
                                    ([] if vehDirSect is None else remDups(vehDirSect.keys())) +
                                    ([] if tracksDirSect is None else remDups(tracksDirSect.keys())))):
                                if self.data['isDebug']:
                                    print self.ID + ':', vehicleName, 'folder from', sname, 'pack is empty.'
                            else:
                                pRecord['whitelist'].add(vehicleName)

                    if self.data['isDebug']:
                        print self.ID + ': config for', sname, 'loaded.'
                snameList = self.skinsData['models'][skinType].keys() + disabledSkins
                for sname in skinsSettings.keys():
                    if sname not in snameList:
                        del skinsSettings[sname]
            if not any(self.skinsData['models'].values()):
                if not quiet:
                    print self.ID + ': no skins configs found, skins module standing down.'
                self.skinsData['enabled'] = False
                for skinType in self.skinsData['priorities']:
                    for key in self.skinsData['priorities'][skinType]:
                        self.skinsData['priorities'][skinType][key] = []
            else:
                for skinType in self.skinsData['priorities']:
                    for key in self.skinsData['priorities'][skinType]:
                        for sname in list(self.skinsData['priorities'][skinType][key]):
                            if sname not in self.skinsData['models'][skinType]:
                                self.skinsData['priorities'][skinType][key].remove(sname)
        else:
            if not quiet:
                print self.ID + ': no skins found, skins module standing down.'
            for skinType in self.skinsData['priorities']:
                for key in self.skinsData['priorities'][skinType]:
                    self.skinsData['priorities'][skinType][key] = []
        loadJson(self.ID, 'skinsPriority', self.skinsData['priorities'], self.configPath, True, quiet=quiet)
        loadJson(self.ID, 'settings', self.settings, self.configPath, True, quiet=quiet)

    def registerSettings(self):
        super(ConfigInterface, self).registerSettings()
        if not hasattr(BigWorld, 'g_modsListApi'):
            return
        # noinspection PyArgumentList
        g_entitiesFactories.addSettings(
            ViewSettings('RemodEnablerUI', RemodEnablerUI, 'RemodEnabler.swf', ViewTypes.WINDOW, None,
                         ScopeTemplates.GLOBAL_SCOPE, False))
        kwargs = dict(
            id='RemodEnablerUI', name=self.i18n['UI_flash_header'], description=self.i18n['UI_flash_header_tooltip'],
            icon='gui/flash/RemodEnabler.png', enabled=self.data['enabled'], login=True, lobby=True,
            callback=lambda: self.loadingProxy is not None or g_appLoader.getDefLobbyApp().loadView(
                SFViewLoadParams('RemodEnablerUI')))
        try:
            BigWorld.g_modsListApi.addModification(**kwargs)
        except AttributeError:
            BigWorld.g_modsListApi.addMod(**kwargs)
        self.isModAdded = True


class RemodEnablerUI(AbstractWindowView):
    def _populate(self):
        super(self.__class__, self)._populate()
        self.modeBackup = g_config.currentMode
        self.remodBackup = g_config.modelsData['selected']['remod']
        self.newRemodData = OrderedDict()

    def py_onRequestSettings(self):
        g_config.readCurrentSettings(not g_config.data['isDebug'])
        texts = {
            'header': {
                'main': g_config.i18n['UI_flash_header'],
                'remodSetup': g_config.i18n['UI_flash_remodSetupBtn'],
                'remodWL': g_config.i18n['UI_flash_remodWLBtn'],
                'remodCreate': g_config.i18n['UI_flash_remodCreateBtn'],
                'skinSetup': g_config.i18n['UI_flash_skinSetupBtn'],
                'priorities': g_config.i18n['UI_flash_skinPriorityBtn']},
            'remodSetupBtn': g_config.i18n['UI_flash_remodSetupBtn'],
            'remodWLBtn': g_config.i18n['UI_flash_remodWLBtn'],
            'remodCreateBtn': g_config.i18n['UI_flash_remodCreateBtn'],
            'skinsSetupBtn': g_config.i18n['UI_flash_skinSetupBtn'],
            'skinsPriorityBtn': g_config.i18n['UI_flash_skinPriorityBtn'],
            'create': {'name': g_config.tb.createLabel('remodCreate_name', 'flash'),
                       'message': g_config.tb.createLabel('remodCreate_message', 'flash')},
            'skinTypes': [g_config.i18n['UI_flash_skinType_' + skinType] for skinType in ('static', 'dynamic')],
            'teams': [g_config.i18n['UI_flash_team_' + team] for team in ('player', 'ally', 'enemy')],
            'remodNames': [],
            'skinNames': [[], []],
            'whiteList': {'addBtn': g_config.i18n['UI_flash_whiteList_addBtn'],
                          'label': g_config.tb.createLabel('whiteList_header', 'flash'),
                          'defStr': g_config.i18n['UI_flash_whiteDropdown_default']},
            'useFor': {'header': g_config.tb.createLabel('useFor_header', 'flash'),
                       'ally': g_config.tb.createLabel('useFor_ally', 'flash'),
                       'enemy': g_config.tb.createLabel('useFor_enemy', 'flash'),
                       'player': g_config.tb.createLabel('useFor_player', 'flash'),
                       'enable': g_config.tb.createLabel('useFor_enable', 'flash')},
            'backBtn': g_config.i18n['UI_flash_backBtn'],
            'saveBtn': g_config.i18n['UI_flash_saveBtn']
        }
        settings = {
            'remods': [],
            'skins': [[], []],
            'priorities': [[g_config.skinsData['priorities'][sType][team] for team in ('player', 'ally', 'enemy')] for
                           sType in ('static', 'dynamic')],
            'whitelists': [],
            'isInHangar': g_config.isInHangar
        }
        for sname in sorted(g_config.modelsData['models']):
            modelsSettings = g_config.settings['remods'][sname]
            texts['remodNames'].append(sname)
            # noinspection PyTypeChecker
            settings['remods'].append({
                'useFor': {key: modelsSettings['swap' + key.capitalize()] for key in ('player', 'ally', 'enemy')},
                'whitelists': [[x for x in str(modelsSettings[team + 'Whitelist']).split(',') if x]
                               for team in ('player', 'ally', 'enemy')]})
        for idx, skinType in enumerate(('', '_dynamic')):
            skins = g_config.settings['skins' + skinType]
            for sname in sorted(g_config.skinsData['models']['static' if not skinType else 'dynamic']):
                sDesc = skins[sname]
                texts['skinNames'][idx].append(sname)
                settings['skins'][idx].append(
                    {'useFor': {k: sDesc['swap' + k.capitalize()] for k in ('player', 'ally', 'enemy')}})
        self.flashObject.as_updateData(texts, settings)

    def py_getRemodData(self):
        vehName = RemodEnablerUI.py_getCurrentVehicleName()
        if vehName:
            try:
                data = self.newRemodData
                data.clear()
                data['authorMessage'] = ''
                for team in ('player', 'ally', 'enemy'):
                    data[team + 'Whitelist'] = [vehName] if vehName else []
                vDesc = g_config.hangarSpace.space.getVehicleEntity().appearance._HangarVehicleAppearance__vDesc
                for key in TankPartNames.ALL + ('engine',):
                    data[key] = OrderedDict()
                for key in TankPartNames.ALL:
                    data[key]['undamaged'] = getattr(vDesc, key).models.undamaged
                chassis = data['chassis']
                for key in ('traces', 'tracks', 'wheels', 'groundNodes', 'trackNodes', 'splineDesc', 'trackParams'):
                    obj = getattr(vDesc.chassis, key)
                    if key != 'splineDesc':
                        obj = str(obj)
                        if key == 'tracks':
                            obj = obj.replace('TrackNode', 'TrackMaterials')
                        elif key == 'trackParams':
                            obj = obj.replace('TrackNode', 'TrackParams')
                    else:
                        obj = 'SplineConfig(%s)' % (', '.join(
                            ("%s=%s" % (attrName.strip('_'), repr(getattr(obj, attrName.strip('_')))) for attrName in
                             SplineConfig.__slots__)))
                    chassis[key] = obj
                chassis['hullPosition'] = vDesc.chassis.hullPosition.tuple()
                chassis['AODecals'] = []
                for decal in vDesc.chassis.AODecals:
                    decDict = {'transform': OrderedDict()}
                    for strIdx in xrange(4):
                        decDict['transform']['row%s' % strIdx] = []
                        for colIdx in xrange(3):
                            decDict['transform']['row%s' % strIdx].append(decal.get(strIdx, colIdx))
                for partName in ('chassis', 'engine'):
                    for key in ('wwsound', 'wwsoundPC', 'wwsoundNPC'):
                        data[partName][key] = getattr(getattr(vDesc, partName).sounds, key)
                pixieID = ''
                for key, value in g_cache._customEffects['exhaust'].iteritems():
                    if value == vDesc.hull.customEffects[0]._selectorDesc:
                        pixieID = key
                        break
                data['hull']['exhaust'] = {'nodes': ' '.join(vDesc.hull.customEffects[0].nodes), 'pixie': pixieID}
                for ids in (('_gunEffects', 'effects'), ('_gunReloadEffects', 'reloadEffect')):
                    for key, value in getattr(g_cache, ids[0]).items():
                        if value == getattr(vDesc.gun, ids[1]):
                            data['gun'][ids[1]] = key
                            break
                exclMask = vDesc.type.camouflage.exclusionMask
                if exclMask:
                    camouflage = data['camouflage'] = OrderedDict()
                    camouflage['exclusionMask'] = exclMask
                    camouflage['tiling'] = vDesc.type.camouflage.tiling
                for partName in TankPartNames.ALL[1:]:
                    part = getattr(vDesc, partName)
                    data[partName]['emblemSlots'] = []
                    exclMask = part.camouflage.exclusionMask if hasattr(part, 'camouflage') else ''
                    if exclMask:
                        camouflage = data[partName]['camouflage'] = OrderedDict()
                        camouflage['exclusionMask'] = exclMask
                        camouflage['tiling'] = part.camouflage.tiling
                    for slot in part.emblemSlots:
                        slotDict = OrderedDict()
                        for key in ('rayStart', 'rayEnd', 'rayUp'):
                            slotDict[key] = getattr(slot, key).tuple()
                        for key in ('size', 'hideIfDamaged', 'type', 'isMirrored', 'isUVProportional', 'emblemId'):
                            slotDict[key] = getattr(slot, key)
                        data[partName]['emblemSlots'].append(slotDict)
            except StandardError:
                SystemMessages.pushMessage(
                    'temp_SM' + g_config.i18n['UI_flash_remodCreate_error'], SystemMessages.SM_TYPE.Warning)
                traceback.print_exc()
        else:
            self.py_sendMessage('', 'Add', 'notSupported')
        modelDesc = getattr(g_config.hangarSpace.space.getVehicleEntity().appearance, 'modelDesc', None)
        if modelDesc is not None:
            return {'isRemod': True, 'name': modelDesc.name, 'message': modelDesc.authorMessage, 'vehicleName': vehName,
                    'whitelists': [
                        [x for x in str(g_config.settings['remods'][modelDesc.name][team + 'Whitelist']).split(',')
                         if x] for team in ('player', 'ally', 'enemy')]}
        else:
            return {'isRemod': False, 'name': '', 'message': '', 'vehicleName': vehName,
                    'whitelists': [[vehName] if vehName else [] for _ in ('player', 'ally', 'enemy')]}

    @staticmethod
    def py_onShowRemod(remodIdx):
        g_config.currentMode = 'remod'
        g_config.modelsData['selected']['remod'] = sorted(g_config.modelsData['models'])[remodIdx]
        refreshCurrentVehicle()

    def py_onModelRestore(self):
        g_config.currentMode = self.modeBackup
        g_config.modelsData['selected']['remod'] = self.remodBackup
        refreshCurrentVehicle()

    @staticmethod
    def py_getCurrentVehicleName():
        vDesc = g_config.hangarSpace.space.getVehicleEntity().appearance._HangarVehicleAppearance__vDesc
        return vDesc.name.split(':')[1].lower()

    def py_onRequestVehicleDelete(self, teamIdx):
        from gui import DialogsInterface
        from gui.Scaleform.daapi.view.dialogs import SimpleDialogMeta, I18nConfirmDialogButtons

        DialogsInterface.showDialog(SimpleDialogMeta(g_config.i18n['UI_flash_WLVehDelete_header'],
                                                     g_config.i18n['UI_flash_WLVehDelete_text'],
                                                     I18nConfirmDialogButtons('common/confirm'), None),
                                    lambda proceed: self.flashObject.as_onVehicleDeleteConfirmed(proceed, teamIdx))

    @staticmethod
    def py_onSaveSettings(settings):
        remodNames = sorted(g_config.modelsData['models'])
        for idx, setObj in enumerate(settings.remods):
            modelsSettings = g_config.settings['remods'][remodNames[idx]]
            for key in ('player', 'ally', 'enemy'):
                modelsSettings['swap' + key.capitalize()] = getattr(setObj.useFor, key)
            for teamIdx, team in enumerate(('player', 'ally', 'enemy')):
                modelsSettings[team + 'Whitelist'] = ','.join(setObj.whitelists[teamIdx])
        for idx, settingsArray in enumerate(settings.skins):
            for nameIdx, setObj in enumerate(settingsArray):
                for key in ('player', 'ally', 'enemy'):
                    g_config.settings['skins' + ('', '_dynamic')[idx]][
                        sorted(g_config.skinsData['models'][('static', 'dynamic')[idx]])[nameIdx]][
                        'swap' + key.capitalize()] = getattr(setObj.useFor, key)
        for idx, prioritiesArray in enumerate(settings.priorities):
            for teamIdx, team in enumerate(('player', 'ally', 'enemy')):
                g_config.skinsData['priorities'][('static', 'dynamic')[idx]][team] = prioritiesArray[teamIdx]
        loadJson(g_config.ID, 'skinsPriority', g_config.skinsData['priorities'], g_config.configPath, True,
                 quiet=not g_config.data['isDebug'])
        loadJson(g_config.ID, 'settings', g_config.settings, g_config.configPath, True, quiet=not g_config.data['isDebug'])
        g_config.readCurrentSettings(not g_config.data['isDebug'])
        refreshCurrentVehicle()

    def py_onCreateRemod(self, settings):
        try:
            if not settings.name:
                SystemMessages.pushMessage('temp_SM' + g_config.i18n['UI_flash_remodCreate_name_empty'],
                                           SystemMessages.SM_TYPE.Warning)
                return
            from collections import OrderedDict
            data = self.newRemodData
            data['authorMessage'] = settings.message
            for teamIdx, team in enumerate(('player', 'ally', 'enemy')):
                data[team + 'Whitelist'] = ','.join(settings.whitelists[teamIdx])
            loadJson(g_config.ID, str(settings.name), data, g_config.configPath + 'remods/', True, False, sort_keys=False)
            g_config.readCurrentSettings()
            SystemMessages.pushMessage(
                'temp_SM' + g_config.i18n['UI_flash_remodCreate_success'], SystemMessages.SM_TYPE.CustomizationForGold)
        except StandardError:
            SystemMessages.pushMessage(
                'temp_SM' + g_config.i18n['UI_flash_remodCreate_error'], SystemMessages.SM_TYPE.Warning)
            traceback.print_exc()

    @staticmethod
    def py_sendMessage(xmlName, action, status):
        SystemMessages.pushMessage(
            'temp_SM%s<b>%s</b>.' % (g_config.i18n['UI_flash_vehicle%s_%s' % (action, status)], xmlName),
            SystemMessages.SM_TYPE.CustomizationForGold)

    def onWindowClose(self):
        self.py_onModelRestore()
        self.destroy()

    @staticmethod
    def py_printLog(*args):
        for arg in args:
            print arg


def lobbyKeyControl(event):
    if not event.isKeyDown() or g_config.isMSAWindowOpen:
        return
    if (g_config.modelsData['enabled'] or g_config.skinsData['enabled']) and checkKeys(g_config.data['ChangeViewHotkey']):
        while True:
            newModeNum = (g_config.possibleModes.index(g_config.currentMode) + 1) % len(g_config.possibleModes)
            g_config.currentMode = g_config.possibleModes[newModeNum]
            if g_config.data.get(g_config.currentMode, True):
                break
        if g_config.data['isDebug']:
            print g_config.ID + ': changing display mode to', g_config.currentMode
        SystemMessages.pushMessage(
            'temp_SM%s<b>%s</b>' % (g_config.i18n['UI_mode'], g_config.i18n['UI_mode_' + g_config.currentMode]),
            SystemMessages.SM_TYPE.Warning)
        refreshCurrentVehicle()
    if checkKeys(g_config.data['CollisionHotkey']):
        if g_config.collisionComparisonEnabled:
            g_config.collisionComparisonEnabled = False
            if g_config.data['isDebug']:
                print g_config.ID + ': disabling collision displaying'
            SystemMessages.pushMessage('temp_SM' + g_config.i18n['UI_disableCollisionComparison'],
                                       SystemMessages.SM_TYPE.CustomizationForGold)
        elif g_config.collisionEnabled:
            g_config.collisionEnabled = False
            g_config.collisionComparisonEnabled = True
            if g_config.data['isDebug']:
                print g_config.ID + ': enabling collision display comparison mode'
            SystemMessages.pushMessage('temp_SM' + g_config.i18n['UI_enableCollisionComparison'],
                                       SystemMessages.SM_TYPE.CustomizationForGold)
        else:
            g_config.collisionEnabled = True
            if g_config.data['isDebug']:
                print g_config.ID + ': enabling collision display'
            SystemMessages.pushMessage('temp_SM' + g_config.i18n['UI_enableCollision'],
                                       SystemMessages.SM_TYPE.CustomizationForGold)
        refreshCurrentVehicle()
    if checkKeys(g_config.data['DynamicSkinHotkey']):
        enabled = g_config.dynamicSkinEnabled
        g_config.dynamicSkinEnabled = not enabled
        SystemMessages.pushMessage(
            'temp_SM' + g_config.i18n['UI_%sableDynamicSkin' % ('en' if not enabled else 'dis')],
            SystemMessages.SM_TYPE.CustomizationForGold)
        refreshCurrentVehicle()
    if g_config.modelsData['enabled'] and checkKeys(g_config.data['SwitchRemodHotkey']):
        if g_config.currentMode != 'remod':
            curTankType = g_config.currentMode
            snameList = sorted(g_config.modelsData['models'].keys()) + ['']
            selected = g_config.modelsData['selected'][curTankType]
            vehName = RemodEnablerUI.py_getCurrentVehicleName()
            if selected.get(vehName) not in snameList:
                snameIdx = 0
            else:
                snameIdx = snameList.index(selected[vehName]) + 1
                if snameIdx == len(snameList):
                    snameIdx = 0
            for Idx in xrange(snameIdx, len(snameList)):
                curPRecord = g_config.modelsData['models'].get(snameList[Idx])
                if snameList[Idx] and vehName not in curPRecord.whitelists[curTankType]:
                    continue
                if vehName in selected:
                    selected[vehName] = getattr(curPRecord, 'name', '')
                loadJson(g_config.ID, 'remodsCache', g_config.modelsData['selected'], g_config.configPath, True,
                         quiet=not g_config.data['isDebug'])
                break
        else:
            snameList = sorted(g_config.modelsData['models'].keys())
            if g_config.modelsData['selected']['remod'] not in snameList:
                snameIdx = 0
            else:
                snameIdx = snameList.index(g_config.modelsData['selected']['remod']) + 1
                if snameIdx == len(snameList):
                    snameIdx = 0
            sname = snameList[snameIdx]
            g_config.modelsData['selected']['remod'] = sname
            loadJson(g_config.ID, 'remodsCache', g_config.modelsData['selected'], g_config.configPath, True,
                     quiet=not g_config.data['isDebug'])
        refreshCurrentVehicle()


def inj_hkKeyEvent(event):
    LobbyApp = g_appLoader.getDefLobbyApp()
    try:
        if LobbyApp and g_config.data['enabled']:
            lobbyKeyControl(event)
    except StandardError:
        print g_config.ID + ': ERROR at inj_hkKeyEvent'
        traceback.print_exc()


InputHandler.g_instance.onKeyDown += inj_hkKeyEvent
InputHandler.g_instance.onKeyUp += inj_hkKeyEvent
g_config = ConfigInterface()
