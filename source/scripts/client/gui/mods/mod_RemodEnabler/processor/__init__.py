import BigWorld
import PYmodsCore
import traceback
from HeroTank import HeroTank
from gui import SystemMessages
from gui.hangar_vehicle_appearance import HangarVehicleAppearance
from items.vehicles import CompositeVehicleDescriptor
from vehicle_systems import appearance_cache
from vehicle_systems.tankStructure import TankPartNames
from .. import g_config
from . import remods, skins_dynamic, skins_static


def skins_find(curVehName, isPlayerVehicle, isAlly, currentMode, skinType):
    if not g_config.skinsData['enabled']:
        return
    curTankType = 'player' if isPlayerVehicle else 'ally' if isAlly else 'enemy'
    if currentMode != 'remod':
        for curSName in g_config.skinsData['priorities'][skinType][curTankType]:
            curPRecord = g_config.skinsData['models'][skinType][curSName]
            if curVehName not in curPRecord['whitelist'] and curVehName.lower() not in curPRecord['whitelist']:
                continue
            return curPRecord


def debugOutput(xmlName, vehName, playerName, modelDesc, staticDesc, dynamicDesc):
    if not g_config.data['isDebug']:
        return
    info = []
    header = g_config.ID + ': %s (%s)' % (xmlName, vehName)
    if playerName is not None:
        header += ', player: ' + playerName
    if modelDesc is not None:
        info.append('modelDesc: ' + modelDesc.name)
    if staticDesc is not None:
        info.append('static skinDesc: ' + staticDesc['name'])
    if dynamicDesc is not None:
        info.append('dynamic skinDesc: ' + dynamicDesc['name'])
    if info:
        print header + ' processed:', ', '.join(info)


def vDesc_process(vehicleID, vDesc, mode):
    if mode == 'battle':
        currentMode = mode
        player = BigWorld.player()
        isPlayerVehicle = vehicleID == player.playerVehicleID
        vehInfoVO = player.guiSessionProvider.getArenaDP().getVehicleInfo(vehicleID)
        playerName = vehInfoVO.player.name
        isAlly = vehInfoVO.team == player.team
    elif mode == 'hangar':
        currentMode = g_config.currentMode
        if currentMode == 'remod' and isinstance(BigWorld.entity(vehicleID), HeroTank):
            currentMode = 'player'
        isPlayerVehicle = currentMode == 'player'
        playerName = None
        isAlly = currentMode == 'ally'
    else:
        return
    xmlName = vDesc.name.split(':')[1].lower()
    modelDesc = remods.find(xmlName, isPlayerVehicle, isAlly, currentMode)
    staticDesc = None
    dynamicDesc = None
    vDesc.installComponent(vDesc.chassis.compactDescr)
    vDesc.installComponent(vDesc.gun.compactDescr)
    if len(vDesc.type.hulls) == 1:
        vDesc.hull = vDesc.type.hulls[0]
    for descr in (vDesc,) if not isinstance(vDesc, CompositeVehicleDescriptor) else (
            vDesc.defaultVehicleDescr, vDesc.siegeVehicleDescr):
        for partName in TankPartNames.ALL + ('engine',):
            try:
                setattr(descr, partName, getattr(descr, partName).copy())
                part = getattr(descr, partName)
                if getattr(part, 'modelsSets', None) is not None:
                    part.modelsSets = part.modelsSets.copy()
            except StandardError:
                traceback.print_exc()
                print partName
    message = None
    collisionNotVisible = not g_config.collisionEnabled and not g_config.collisionComparisonEnabled
    vehNation, vehName = vDesc.chassis.models.undamaged.split('/')[1:3]
    vehDefNation = vDesc.chassis.hitTester.bspModelName.split('/')[1]
    if modelDesc is None:
        if g_config.skinsData['found']:
            if vehNation == vehDefNation:
                dynamicDesc = skins_find(vehName, isPlayerVehicle, isAlly, currentMode, 'dynamic')
                if dynamicDesc is not None:
                    skins_dynamic.create(vehicleID, vDesc, dynamicDesc['name'], mode == 'hangar' and (
                            g_config.dynamicSkinEnabled and not g_config.collisionComparisonEnabled))
                    if g_config.dynamicSkinEnabled and collisionNotVisible:
                        message = g_config.i18n['UI_install_skin_dynamic'] + '<b>' + dynamicDesc['name'] + '</b>.'
                staticDesc = skins_find(vehName, isPlayerVehicle, isAlly, currentMode, 'static')
                if staticDesc is not None:
                    skins_static.apply(vDesc, staticDesc['name'])
            elif g_config.data['isDebug']:
                    print g_config.ID + ': unknown vehicle nation for', vehName + ':', vehNation
            if g_config.data['isDebug'] and (dynamicDesc is None or not g_config.dynamicSkinEnabled) and collisionNotVisible:
                if staticDesc is not None:
                    message = g_config.i18n['UI_install_skin'] + '<b>' + staticDesc['name'] + '</b>.'
                else:
                    message = g_config.i18n['UI_install_default']
    else:
        for descr in (vDesc,) if not isinstance(vDesc, CompositeVehicleDescriptor) else (
                vDesc._CompositeVehicleDescriptor__vehicleDescr, vDesc._CompositeVehicleDescriptor__siegeDescr):
            remods.apply(descr, modelDesc)
        if collisionNotVisible:
            message = g_config.i18n['UI_install_remod'] + '<b>' + modelDesc.name + '</b>.\n' + modelDesc.authorMessage
    if message is not None and mode == 'hangar':
        SystemMessages.pushMessage('temp_SM' + message, SystemMessages.SM_TYPE.CustomizationForGold)
    debugOutput(xmlName, vehName, playerName, modelDesc, staticDesc, dynamicDesc)
    return modelDesc


@PYmodsCore.overrideMethod(appearance_cache._AppearanceCache, '_AppearanceCache__cacheApperance')
def new_cacheAppearance(base, self, vId, info, *args):
    if g_config.data['enabled']:
        vDesc_process(vId, info.typeDescr, 'battle')
    return base(self, vId, info, *args)


@PYmodsCore.overrideMethod(HangarVehicleAppearance, '_HangarVehicleAppearance__startBuild')
def new_startBuild(base, self, vDesc, vState):
    if g_config.data['enabled']:
        self.modelDesc = vDesc_process(self._HangarVehicleAppearance__vEntity.id, vDesc, 'hangar')
    base(self, vDesc, vState)
