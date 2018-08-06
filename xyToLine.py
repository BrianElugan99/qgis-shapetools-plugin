import os
import re
import math
from geographiclib.geodesic import Geodesic

from qgis.core import QgsCoordinateTransform, QgsPointXY, QgsFeature, QgsGeometry, QgsProject, QgsWkbTypes

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QUrl, QCoreApplication

from qgis.core import (QgsProcessing,
    QgsProcessingException,
    QgsFeatureSink,
    QgsProcessingAlgorithm,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterField,
    QgsProcessingParameterFeatureSink)

from .LatLon import LatLon
from .settings import settings, epsg4326
#import traceback

def tr(string):
    return QCoreApplication.translate('Processing', string)

class XYToLineAlgorithm(QgsProcessingAlgorithm):
    """
    Algorithm for creating lines from two coordinates within a record.
    """

    LINE_TYPE = ['Geodesic','Great Circle','Simple Line']
    PrmInputLayer = 'InputLayer'
    PrmOutputPointLayer = 'OutputPointLayer'
    PrmOutputLineLayer = 'OutputLineLayer'
    PrmInputCRS = 'InputCRS'
    PrmOutputCRS = 'OutputCRS'
    PrmLineType = 'LineType'
    PrmStartUseLayerGeom = 'StartUseLayerGeom'
    PrmStartXField = 'StartXField'
    PrmStartYField = 'StartYField'
    PrmEndUseLayerGeom = 'EndUseLayerGeom'
    PrmEndXField = 'EndXField'
    PrmEndYField = 'EndYField'
    PrmShowStartPoint = 'ShowStartPoint'
    PrmShowEndPoint = 'ShowEndPoint'
    PrmDateLineBreak = 'DateLineBreak'
    geod = Geodesic.WGS84

    def initAlgorithm(self, config):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.PrmInputLayer,
                tr('Input layer'),
                [QgsProcessing.TypeFile|QgsProcessing.TypeVectorPoint])
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.PrmInputCRS,
                tr('Input CRS for coordinates within the vector fields'),
                'ProjectCrs')
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.PrmOutputCRS,
                tr('Output layer CRS'),
                'ProjectCrs')
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.PrmLineType,
                tr('Line type'),
                options=self.LINE_TYPE,
                defaultValue=0,
                optional=False)
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PrmStartUseLayerGeom,
                tr('Use the point geometry for the line starting point'),
                False,
                optional=True)
            )
        self.addParameter(
            QgsProcessingParameterField(
                self.PrmStartXField,
                tr('Starting X Field (lon)'),
                parentLayerParameterName=self.PrmInputLayer,
                type=QgsProcessingParameterField.Any,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PrmStartYField,
                tr('Starting Y Field (lat)'),
                parentLayerParameterName=self.PrmInputLayer,
                type=QgsProcessingParameterField.Any,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PrmEndUseLayerGeom,
                tr('Use the point geometry for the line ending point'),
                False,
                optional=True)
            )
        self.addParameter(
            QgsProcessingParameterField(
                self.PrmEndXField,
                tr('Ending X Field (lon)'),
                parentLayerParameterName=self.PrmInputLayer,
                type=QgsProcessingParameterField.Any,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PrmEndYField,
                tr('Ending Y Field (lat)'),
                parentLayerParameterName=self.PrmInputLayer,
                type=QgsProcessingParameterField.Any,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PrmShowStartPoint,
                tr('Show starting point'),
                True,
                optional=True)
            )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PrmShowEndPoint,
                tr('Show ending point'),
                True,
                optional=True)
            )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PrmDateLineBreak,
                tr('Break lines at -180, 180 boundary for better rendering'),
                False,
                optional=True)
            )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.PrmOutputLineLayer,
                tr('Output line layer'))
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.PrmOutputPointLayer,
                tr('Output point layer'),
                optional=True,
                createByDefault=False)
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.PrmInputLayer, context)
        sourceCrs = self.parameterAsCrs(parameters, self.PrmInputCRS, context)
        sinkCrs = self.parameterAsCrs(parameters, self.PrmOutputCRS, context)
        lineType = self.parameterAsInt(parameters, self.PrmLineType, context)
        startUseGeom =  self.parameterAsBool(parameters, self.PrmStartUseLayerGeom, context)
        startXcol = self.parameterAsString(parameters, self.PrmStartXField, context)
        startYcol = self.parameterAsString(parameters, self.PrmStartYField, context)
        endUseGeom =  self.parameterAsBool(parameters, self.PrmEndUseLayerGeom, context)
        endXcol = self.parameterAsString(parameters, self.PrmEndXField, context)
        endYcol = self.parameterAsString(parameters, self.PrmEndYField, context)
        showStart =  self.parameterAsBool(parameters, self.PrmShowStartPoint, context)
        showEnd =  self.parameterAsBool(parameters, self.PrmShowEndPoint, context)
        dateLine =  self.parameterAsBool(parameters, self.PrmDateLineBreak, context)
        
        if dateLine and lineType <= 1:
            isMultiPart = True
        else:
            isMultiPart = False
        
        if isMultiPart:
            (lineSink, lineDest_id) = self.parameterAsSink(parameters,
                self.PrmOutputLineLayer, context, source.fields(),
                QgsWkbTypes.MultiLineString, sinkCrs)
        else:
            (lineSink, lineDest_id) = self.parameterAsSink(parameters,
                self.PrmOutputLineLayer, context, source.fields(),
                QgsWkbTypes.LineString, sinkCrs)
        (ptSink, ptDest_id) = self.parameterAsSink(parameters,
            self.PrmOutputPointLayer, context, source.fields(),
            QgsWkbTypes.Point, sinkCrs)
            
        if not ptSink:
            if showStart or showEnd:
                feedback.pushInfo(tr('Output point layer was set to [skip output]. No point layer will be generated.'))
            showStart = False
            showEnd = False
        if (startUseGeom or endUseGeom) and (source.wkbType() != QgsWkbTypes.Point):
            msg = tr('In order to use the layer geometry for the start or ending points, the input layer must be of type Point')
            feedback.reportError(msg)
            raise QgsProcessingException(msg)
            
        if (not startUseGeom and (not startXcol or not startYcol)) or (not endUseGeom and (not endXcol or not endYcol)):
            msg = tr('Please select valid starting and ending point columns')
            feedback.reportError(msg)
            raise QgsProcessingException(msg)
        if source.wkbType() != QgsWkbTypes.Point and (startUseGeom or endUseGeom):
            msg = tr("In order to select the input layer's geometry as a beginning or ending point it must be a Point vector layer.")
            feedback.reportError(msg)
            raise QgsProcessingException(msg)
            
        # Set up CRS transformations
        geomCrs = source.sourceCrs()
        if (startUseGeom or endUseGeom) and (geomCrs != epsg4326):
            geomTo4326 = QgsCoordinateTransform(geomCrs, epsg4326, QgsProject.instance())
        if sourceCrs != epsg4326:
            sourceTo4326 = QgsCoordinateTransform(sourceCrs, epsg4326, QgsProject.instance())
        if sinkCrs != epsg4326:
            toSinkCrs = QgsCoordinateTransform(epsg4326, sinkCrs, QgsProject.instance())
            
            
        featureCount = source.featureCount()
        total = 100.0 / featureCount if featureCount else 0
        numBad = 0
        maxseglen = settings.maxSegLength*1000.0
        maxSegments = settings.maxSegments
        
        iterator = source.getFeatures()
        for cnt, feature in enumerate(iterator):
            if feedback.isCanceled():
                break
            try:
                if startUseGeom:
                    ptStart = feature.geometry().asPoint()
                    if geomCrs != epsg4326:
                        ptStart = geomTo4326.transform(ptStart)
                else:
                    ptStart = QgsPointXY(float(feature[startXcol]), float(feature[startYcol]))
                    if sourceCrs != epsg4326:
                        ptStart = sourceTo4326.transform(ptStart)
                if endUseGeom:
                    ptEnd = feature.geometry().asPoint()
                    if geomCrs != epsg4326:
                        ptEnd = geomTo4326.transform(ptEnd)
                else:
                    ptEnd = QgsPointXY(float(feature[endXcol]), float(feature[endYcol]))
                    if sourceCrs != epsg4326:
                        ptEnd = sourceTo4326.transform(ptEnd)
                pts = [ptStart]
                if lineType == 0: # Geodesic
                    l = self.geod.InverseLine(ptStart.y(), ptStart.x(), ptEnd.y(), ptEnd.x())
                    if l.s13 > maxseglen:
                        n = int(math.ceil(l.s13 / maxseglen))
                        if n > maxSegments:
                            n = maxSegments
                        seglen = l.s13 / n
                        for i in range(1,n+1):
                            s = seglen * i
                            g = l.Position(s, Geodesic.LATITUDE | Geodesic.LONGITUDE)
                            pts.append( QgsPointXY(g['lon2'], g['lat2']) )
                elif lineType == 1: # Great circle
                    pts = LatLon.getPointsOnLine(ptStart.y(), ptStart.x(),
                        ptEnd.y(), ptEnd.x(),
                        settings.maxSegLength*1000.0, # Put it in meters
                        settings.maxSegments+1)
                    pts.append(ptEnd)
                else: # Simple line
                    pts.append(ptEnd)
                f = QgsFeature()
                if isMultiPart:
                    outseg = self.checkCrossings(pts)
                    if sinkCrs != epsg4326: # Convert each point to the output CRS
                        for y in range(len(outseg)):
                            for x, pt in enumerate(outseg[y]):
                                outseg[y][x] = toSinkCrs.transform(pt)
                    f.setGeometry(QgsGeometry.fromMultiPolylineXY(outseg))
                else:
                    if sinkCrs != epsg4326: # Convert each point to the output CRS
                        for x, pt in enumerate(pts):
                            pts[x] = toSinkCrs.transform(pt)
                    f.setGeometry(QgsGeometry.fromPolylineXY(pts))
                f.setAttributes(feature.attributes())
                lineSink.addFeature(f)
                
                if showStart:
                    f = QgsFeature()
                    f.setGeometry(QgsGeometry.fromPointXY(toSinkCrs.transform(ptStart)))
                    f.setAttributes(feature.attributes())
                    ptSink.addFeature(f)
                if showEnd:
                    f = QgsFeature()
                    f.setGeometry(QgsGeometry.fromPointXY(toSinkCrs.transform(ptEnd)))
                    f.setAttributes(feature.attributes())
                    ptSink.addFeature(f)
            except:
                numBad += 1
                '''s = traceback.format_exc()
                feedback.pushInfo(s)'''
                
            feedback.setProgress(int(cnt * total))
            
        if numBad > 0:
            feedback.pushInfo(tr("{} out of {} features from input layer failed to process correctly.".format(numBad, featureCount)))
        
            
        return {self.PrmOutputLineLayer: lineDest_id, self.PrmOutputPointLayer: ptDest_id}
    
    def checkCrossings(self, pts):
        outseg = []
        ptlen = len(pts)
        pts2 = [pts[0]]
        for i in range(1,ptlen):
            if pts[i-1].x() < -130 and pts[i].x() > 130: # We have crossed the date line going west
                ld = self.geod.Inverse(pts[i-1].y(), pts[i-1].x(), pts[i].y(), pts[i].x())
                try:
                    (intrlat, intrlon) = intersection_point(-89,-180, 0, pts[i-1].y(), pts[i-1].x(), ld['azi1'])
                    ptnew = QgsPointXY(-180, intrlat)
                    pts2.append(ptnew)
                    outseg.append(pts2)
                    ptnew = QgsPointXY(180, intrlat)
                    pts2 = [ptnew]
                except:
                    pts2.append(pts[i])
            if pts[i-1].x() > 130 and pts[i].x() < -130: # We have crossed the date line going east
                ld = self.geod.Inverse(pts[i-1].y(), pts[i-1].x(), pts[i].y(), pts[i].x())
                try:
                    (intrlat, intrlon) = intersection_point(-89,180, 0, pts[i-1].y(), pts[i-1].x(), ld['azi1'])
                    ptnew = QgsPointXY(180, intrlat)
                    pts2.append(ptnew)
                    outseg.append(pts2)
                    ptnew = QgsPointXY(-180, intrlat)
                    pts2 = [ptnew]
                except:
                    pts2.append(pts[i])
            else:
                pts2.append(pts[i])
        outseg.append(pts2)

        return(outseg)
        
    def name(self):
        return 'xy2line'

    def icon(self):
        return QIcon(os.path.dirname(__file__) + '/images/xyline.png')
    
    def displayName(self):
        return tr('XY to line')
    
    def group(self):
        return tr('Vector geometry')
        
    def groupId(self):
        return 'vectorgeometry'
        
    def helpUrl(self):
        file = os.path.dirname(__file__)+'/index.html'
        if not os.path.exists(file):
            return ''
        return QUrl.fromLocalFile(file).toString(QUrl.FullyEncoded)
    
    def shortHelpString(self):
        file = os.path.dirname(__file__)+'/doc/XYtoLineAlgorithm.help'
        if not os.path.exists(file):
            return ''
        with open(file) as helpf:
            help=helpf.read()
        return help
        
    def createInstance(self):
        return XYToLineAlgorithm()

def intersection_point(lat1, lon1, bearing1, lat2, lon2, bearing2):
    o1 = math.radians(lat1)
    lam1 = math.radians(lon1)
    o2 = math.radians(lat2)
    lam2 = math.radians(lon2)
    bo_13 = math.radians(bearing1)
    bo_23 = math.radians(bearing2)
    
    diff_fo = o2 - o1
    diff_la = lam2 - lam1
    d12 = 2 * math.asin(math.sqrt(math.sin(diff_fo / 2) * math.sin(diff_fo / 2) + math.cos(o1) * math.cos(o2) * math.sin(diff_la / 2) * math.sin(diff_la / 2)))
    if d12 == 0: # intersection_not_found
        raise ValueError('Intersection not found')

    print("bo_2 numerator: {}".format(math.sin(o1) - math.sin(o2) * math.cos(d12)))
    print("bo_2 denominator: {}".format(math.sin(d12) * math.cos(o2)))
    bo_1 = math.acos((math.sin(o2) - math.sin(o1) * math.cos(d12)) / (math.sin(d12) * math.cos(o1)))
    bo_2 = math.acos((math.sin(o1) - math.sin(o2) * math.cos(d12)) / (math.sin(d12) * math.cos(o2)))
    if math.sin(lam2 - lam1) > 0:
        bo_12 = bo_1
        bo_21 = 2 * math.pi - bo_2
    else:
        bo_12 = 2 * math.pi - bo_1
        bo_21 = bo_2
    a_1 = ((bo_13 - bo_12 + math.pi) % (2 * math.pi)) - math.pi
    a_2 = ((bo_21 - bo_23 + math.pi) % (2 * math.pi)) - math.pi
    if (math.sin(a_1) == 0) and (math.sin(a_2) == 0): # infinite intersections
        raise ValueError('Intersection not found')
    if math.sin(a_1) * math.sin(a_2) < 0: # ambiguous intersection
        raise ValueError('Intersection not found')

    a_3 = math.acos(-math.cos(a_1) * math.cos(a_2) + math.sin(a_1) * math.sin(a_2) * math.cos(d12))
    be_13 = math.atan2(math.sin(d12) * math.sin(a_1) * math.sin(a_2), math.cos(a_2) + math.cos(a_1) * math.cos(a_3))
    fo_3 = math.asin(math.sin(o1) * math.cos(be_13) + math.cos(o1) * math.sin(be_13) * math.cos(bo_13))
    diff_lam13 = math.atan2(math.sin(bo_13) * math.sin(be_13) * math.cos(o1), math.cos(be_13) - math.sin(o1) * math.sin(fo_3))
    la_3 = lam1 + diff_lam13

    return (math.degrees(fo_3), math.degrees(la_3))
