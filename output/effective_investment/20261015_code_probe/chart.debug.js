(function(c, undefined ) {
	'use strict';
	var display =  function(){
		var newdiv = document.createElement('div');
		newdiv.setAttribute('id', 'chart_debug_id');
		
	    newdiv.style.position = 'fixed';
	    newdiv.style.bottom = '60px';
	    newdiv.style.right = '0px';
		
		newdiv.style.background = '#EAD';
		newdiv.style.border = '4px solid #000';
		newdiv.innerHTML = '<h4>Chart configurations missing <br/> for chart.js:</h4><ul style="list-style-position: inside" id="chart_missing"></ul>';
		document.body.appendChild(newdiv);
		return newdiv;
	}
	
	var error = function(variable){
		var element = document.getElementById('chart_debug_id');
		if(!element){
			element = display();
		}
		element = document.getElementById('chart_missing');
		var li = document.createElement('li');
		li.innerHTML = variable;
		element.appendChild(li);
	}
	
	c.check = function(id){
		if(c.legacy){
			try{
				if(typeof eval(id.replace(new RegExp('\\\\.', 'g'), '_')+'_width') == 'undefined' || typeof eval(id.replace(new RegExp('\\\\.', 'g'), '_')+'_height') == 'undefined' ){
					error(id);
				}
			}catch(e){
				error(id);
			}
		}
	}
}(Chart));