var Chart = window.Chart || {};
(function(c, $, undefined ) {
	"use strict";
	
	var themes = [],
	    data = {},
		defaults = {
			width    : '100%',
			height   : '100%',
			u        : null,
			theme    : 'common'
		};
	c.version = 1;
	var themesRegistered = false;
	
	var isSlide = function(id){
		return id.indexOf("_slide", id.length - "_slide".length) !== -1
	}
	
	c.init = function(d){
		data = d;
	};
	
	c.addTheme = function(theme){
		themes.push(theme);
	};
	
	c.get = function(id){
		if(data[id]){
			if(!data[id].rdy)
				data[id] = $.extend({rdy:true}, defaults, data[id]);
		}else
			data[id] = $.extend({rdy:true}, defaults);
		
		return data[id];
	};
	
	c.decision = function(id, dv){
		var p = c.get(id);
		Wicket.Ajax.get({'u' : p.u, 'ep' : {'dv': dv}, 'sh' : [function(){ if(typeof c.sh === 'function') c.sh(p, dv);}]});
	};
	
	c.applyTheme = function(id){
		if(!themesRegistered){
			FusionCharts.register('theme', themes);
			themesRegistered = true;
		}
		var ch = c.get(id);
		if(ch.theme)
			FusionCharts.items[id].setChartAttribute("theme", ch.theme);
	};
	c.width = function(id){
		if(isSlide(id))
			return '100%';
		if(c.version > 1) 
			return c.get(id).width;
		return window[id.replace(new RegExp('\\.', 'g'), '_')+'_width'];
	}
	c.height = function(id){
		if(isSlide(id))
			return '100%';
		if(c.version > 1)
			return c.get(id).height;
		return window[id.replace(new RegExp('\\.', 'g'), '_')+'_height'];
	}
	c.post = function(id, d){
	    if(c.get(id).post !== undefined)
	        c.get(id).post(d)
	    return d;
	}
	c.update = function(id, data){
		if(typeof data === 'string' || data instanceof String)
			FusionCharts.items[id].setXMLData(data);
		else
			FusionCharts.items[id].setJSONData(c.post(id, data));
		c.applyTheme(id);
	}
	c.create = function(cid, ctype, data, target){
		if(FusionCharts.items[cid])
			FusionCharts.items[cid].dispose();
		
		FusionCharts.ready(function() {
			if(!themesRegistered){
				FusionCharts.register('theme', themes);
				themesRegistered = true;
			}
			var fc = new FusionCharts({
				id : cid,
				type : ctype,
				dataSource: c.post(cid, data),
				width: c.width(cid),
				height: c.height(cid),
				containerBackgroundOpacity: '0',
				renderAt: target
			});
			var ch = c.get(cid);
			if(ch.theme)
				fc.setChartAttribute("theme", ch.theme);
			fc.render();
		});
	}
}(Chart, jQuery));