import numpy
import wx
import csv
import os
import os.path
import math
from avoplot import plugins, series, controls, subplots
from avoplot.persist import PersistentStorage
from avoplot.plugins import AvoPlotPluginSimple
from avoplot.subplots import AvoPlotXYSubplot
from avoplot.series import XYDataSeries

from avoplot.gui import widgets

from doas.spectrum_loader import SpectrumIO, UnableToLoad

plugin_is_GPL_compatible = True

class FTIRSpectrumSubplot(AvoPlotXYSubplot):
    def my_init(self):
        ax = self.get_mpl_axes()
        ax.set_xlabel('Wavenumber (cm-1)')
        ax.set_ylabel('Absorbance')
        
#define new data series type for FTIR data
class FTIRSpectrumData(XYDataSeries):
    def __init__(self, *args, **kwargs):
        super(FTIRSpectrumData, self).__init__(*args, **kwargs)
        
        #add a control for this data series to allow the user to change the 
        #frequency of the wave using a slider.
        self.add_control_panel(BackgroundCalcCtrl(self))    
    
    @staticmethod
    def get_supported_subplot_type():
        return FTIRSpectrumSubplot



class FTIRPlugin(plugins.AvoPlotPluginSimple):
    def __init__(self):
        super(FTIRPlugin, self).__init__("FTIR Plugin Kayla", FTIRSpectrumData)
        
        self.set_menu_entry(['FTIR', 'New Spectrum'], "Plot an FTIR spectrum")
        
        
    def plot_into_subplot(self, subplot):
        self.wavenumber, self.absorbance = self.load_ftir_file()
        if self.wavenumber is None:
            return False

        
        data_series = FTIRSpectrumData("FTIR Spectrum", 
                                       xdata=self.wavenumber, 
                                       ydata=self.absorbance)
        
        subplot.add_data_series(data_series)
        
        return True
    
    
    
    def load_ftir_file(self):
        persist = PersistentStorage()

        try:
            last_path_used = persist.get_value("ftir_spectra_dir")
        except KeyError:
            last_path_used = ""
        
        #get filename to open
        spectrum_file = wx.FileSelector("Choose spectrum file to open", 
                                        default_path=last_path_used)
        if spectrum_file == "":
            return None
        
        persist.set_value("ftir_spectra_dir", os.path.dirname(spectrum_file))
        
        reader = csv.reader(open(spectrum_file, "rb"), dialect="excel") 
        
        wavenumber = []
        absorbance = []

        for line in reader:
             wavenumber.append(float(line[0]))
             absorbance.append(float(line[1]))        
        
        try:        
            return wavenumber, absorbance
        except Exception,e:
            print e.args
            wx.MessageBox("Unable to load spectrum file \'%s\'. "
                          "Unrecognised file format."%spectrum_file, 
                          "AvoPlot", wx.ICON_ERROR)
            return None
        

#Start Extra Control Panel Functions -- created after adv_sine_wave example in AvoPlot documentation
class BackgroundCalcCtrl(controls.AvoPlotControlPanelBase):
    """
    Control panel for sine wave data series allowing their frequency to 
    be changed using a slider.
    """
    def __init__(self, series):
        #call the parent class's __init__ method, passing it the name that we
        #want to appear on the control panels tab.
        super(BackgroundCalcCtrl, self).__init__("Background Fit")
        
        #store the data series object that this control panel is associated with, 
        #so that we can access it later
        self.series = series
    
    
    def setup(self, parent):
        self.plot_obj = parent
        spec_type = classify_spectrum
        wx.Panel.__init__(self, parent, wx.ID_ANY,style=wx.BORDER_SIMPLE)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        h2o_button = wx.Button(self, wx.ID_ANY, "Fit H2O")
        self.peak_height_text = wx.StaticText(self, -1, "Peak Height:\n")
        sizer.Add(h2o_button, 0, wx.ALIGN_TOP|wx.ALL,border=10)
        sizer.Add(wx.StaticText(self, -1, "Spec Type:\n%s"%spec_type), 0, wx.ALIGN_TOP|wx.ALL,border=10)
        sizer.Add(self.peak_height_text,0, wx.ALIGN_TOP|wx.ALL,border=10)
        wx.EVT_BUTTON(self, h2o_button.GetId(), self.fit_h2o)
        
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.SetAutoLayout(True)
    
    def set_peak_height(self, height):
        self.peak_height_text.SetLabel("Peak Height:\n%f"%height)
    
    def fit_h2o(self, evnt):
        try:
            wx.BeginBusyCursor()
            bkgd = fit_h2o_peak(self.wavenumber, self.absorbance, self.axes, plot_fit=True)
            peak_height = calc_h2o_peak_height(self.wavenumber, self.absorbance, bkgd)
            self.control_panel.set_peak_height(peak_height)
            
            self.canvas.draw()
            self.canvas.gui_repaint()
        finally:
            wx.EndBusyCursor()
            
def get_h2o_fitting_points(xdata, ydata, bkgd_func=None, target_wavenumber_range=200, tolerance=30):
    
    #initialise the cropping limits
    l_crop = 2200
    r_crop = 4000
    
    master_xdata = numpy.array(xdata)
    master_ydata = numpy.array(ydata)   
     
    data_mask = numpy.where(numpy.logical_and(master_xdata > l_crop, master_xdata <=r_crop))
    xdata = master_xdata[data_mask]
    ydata = master_ydata[data_mask]
       
    peak_idx = numpy.argmax(ydata)
    
    l_min = numpy.argmin(ydata[:peak_idx])
    r_min = numpy.argmin(ydata[peak_idx:])+peak_idx
        
    while (abs(xdata[l_min]-l_crop - target_wavenumber_range) > tolerance or
          abs(r_crop - xdata[r_min] - target_wavenumber_range) > tolerance):
        
        l_crop -= target_wavenumber_range - (xdata[l_min]-l_crop)
        r_crop -= (r_crop - xdata[r_min]) - target_wavenumber_range
        
        data_mask = numpy.where(numpy.logical_and(master_xdata > l_crop, master_xdata <=r_crop))
        xdata = master_xdata[data_mask]
        ydata = master_ydata[data_mask]
           
        peak_idx = numpy.argmax(ydata)
        
        if bkgd_func is None:
            if len(ydata[:peak_idx])>0:
                l_min = numpy.argmin(ydata[:peak_idx])
            else:
                l_min = 0
                break
        else:
            l_min = numpy.argmin(ydata[:peak_idx]-bkgd_func(xdata[:peak_idx]))
        r_min = numpy.argmin(ydata[peak_idx:])+peak_idx
    
    if xdata[l_min] < 2000:
        if bkgd_func is not None:
            raise ValueError("Failed to find fitting points")
        return get_h2o_fitting_points(master_xdata, master_ydata, bkgd_func=get_global_bkgd(xdata, ydata))
        
    fit_xdata = numpy.concatenate((xdata[:l_min],xdata[r_min:]))
    fit_ydata = numpy.concatenate((ydata[:l_min],ydata[r_min:]))
    return fit_xdata, fit_ydata


def classify_spectrum(xdata, ydata):
    
    #first find the water peak
    l_crop = 2200
    r_crop = 4000
    
    master_xdata = numpy.array(xdata)
    master_ydata = numpy.array(ydata)   
     
    data_mask = numpy.where(numpy.logical_and(master_xdata > l_crop, master_xdata <=r_crop))
    xdata = master_xdata[data_mask]
    ydata = master_ydata[data_mask]
       
    peak_idx = numpy.argmax(ydata)
    global_peak_idx = peak_idx + numpy.argmin(master_xdata-l_crop)
    
    #now find the global minimum
    min_y_idx = numpy.argmin(master_ydata[:global_peak_idx])
    min_y_xvalue = master_xdata[min_y_idx]
    r_min_idx = numpy.argmin(ydata[peak_idx:])+peak_idx
    
    rh_fit_line_param = numpy.polyfit(xdata[r_min_idx:], ydata[r_min_idx:],1)
    rh_fit_line=numpy.poly1d(rh_fit_line_param)
    if rh_fit_line(min_y_xvalue) < master_ydata[min_y_idx]:
        return "Well behaved"
    else:
        return "Low H2O"
    


def get_global_bkgd(xdata, ydata):
    master_xdata = numpy.array(xdata)
    master_ydata = numpy.array(ydata)
    line_grad = numpy.gradient(numpy.array(ydata[numpy.argmax(ydata):]))
    mask = numpy.where(line_grad > 0)
    first_min = ydata[mask[0][0]+numpy.argmax(ydata)]
    print "first min at ",xdata[mask[0][0]]
    
    data_mask = numpy.where(numpy.logical_and(master_xdata > 2200, master_xdata <=4000))
    #xdata = master_xdata[data_mask]
    #ydata = master_ydata[data_mask]
    last_val = master_ydata[-1]
    
    polyfit_params = numpy.polyfit(numpy.array([xdata[mask[0][0]],xdata[-1]]), numpy.array([first_min, last_val]), 1)
    print "polyfit params = ",polyfit_params
    if polyfit_params[0] < 0:
        print "returning zeros as backgrounds"
        return lambda x: numpy.zeros_like(x)
    
    return numpy.poly1d(polyfit_params)
    
    

def fit_h2o_peak(xdata, ydata, axes, plot_fit=True):
    #master_xdata = numpy.array(xdata)
    #master_ydata = numpy.array(ydata)
    #plot(master_xdata, master_ydata)
    if len(xdata) != len(ydata):
        raise ValueError, "Lengths of xdata and ydata must match"
    
    #crop the x and y data to the fitting range
    fit_xdata, fit_ydata = get_h2o_fitting_points(xdata, ydata)
    fit_ydata = fit_ydata
    
    polyfit_params = numpy.polyfit(fit_xdata, fit_ydata, 3)
    bkgd_function = numpy.poly1d(polyfit_params)
    
    axes.plot(fit_xdata,fit_ydata,'+')
    bkgd_xdata = numpy.arange(fit_xdata[0], fit_xdata[-1])
    axes.plot(bkgd_xdata, bkgd_function(bkgd_xdata))
    
    return bkgd_function


def calc_h2o_peak_height(xdata, ydata, bkgd_func):
    l_crop = 2200
    r_crop = 4000
    
    master_xdata = numpy.array(xdata)
    master_ydata = numpy.array(ydata)   
     
    data_mask = numpy.where(numpy.logical_and(master_xdata > l_crop, master_xdata <=r_crop))
    xdata = master_xdata[data_mask]
    ydata = master_ydata[data_mask]
    peak_idx = numpy.argmax(ydata)
    global_peak_idx = peak_idx + numpy.argmin(numpy.abs(master_xdata-l_crop))
    print "peak index = %d, global index = %d"%(peak_idx, global_peak_idx)
    return master_ydata[global_peak_idx] - bkgd_func(master_xdata[global_peak_idx])
    
    
    
    

#class FTIRSpecPlot(PlotPanelBase):
#    
#    def __init__(self, parent, filename):            
#        self.wavenumber, self.absorbance = load_ftir_file(filename)        
#        print classify_spectrum(self.wavenumber, self.absorbance)
#        PlotPanelBase.__init__(self,parent, os.path.basename(filename))
#        self.control_panel = FTIRFittingPanel(self, classify_spectrum(self.wavenumber, self.absorbance))
#        self.h_sizer.Insert(0,self.control_panel, flag=wx.ALIGN_LEFT)
#        
#        self.create_plot()
#        
#    
#    def fit_h2o(self, evnt):
#        try:
#            wx.BeginBusyCursor()
#            bkgd = fit_h2o_peak(self.wavenumber, self.absorbance, self.axes, plot_fit=True)
#            peak_height = calc_h2o_peak_height(self.wavenumber, self.absorbance, bkgd)
#            self.control_panel.set_peak_height(peak_height)
#            
#            self.canvas.draw()
#            self.canvas.gui_repaint()
#        finally:
#            wx.EndBusyCursor()
#    
#    def create_plot(self):
#        self.axes.plot(self.wavenumber, self.absorbance)
#        self.axes.set_xlim((self.axes.get_xlim()[1],self.axes.get_xlim()[0]))
#        self.axes.set_xlabel("Wavenumber")
#        self.axes.set_ylabel("Absorbance")


plugins.register(FTIRPlugin())