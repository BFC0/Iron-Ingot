(function(c, $, undefined ) {
	"use strict";
	c.version = 2;
	
	var mstheme = 
	{
		chart: {
				plotToolText: "$dataValue - $seriesName",
		}
	}

	
	c.addTheme({
		name: 'common',
		theme: {
			base: {
				chart: {
					bgColor: '#ffffff',
					baseFontSize: '12',
					baseFont: '-apple-system, BlinkMacSystemFont, Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", "Segoe UI", sans-serif',
					outCnvBaseFont: '-apple-system, BlinkMacSystemFont, Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", "Segoe UI", sans-serif',
					labelFontColor : "#000000",

					showLegend: '1',
		            legendBorderColor: '#ffffff',
		            legendShadow: '0',

		            legendIconScale: '1.0',
		            legendBgAlpha: '0',
		            legendCaption: '',	
					canvasBgColor: '#eeeeee',
					canvasBgAlpha: '30',
					canvasBorderColor: '#ffffff',
					paletteColors: '#FFAB40, #448AFF, #6D30FE, #2962FF, #FF5252, #FDD835, #536DFE, #FF2751, #B2FF59, #FF4081, #5E35B1, #F37720',
					
					useRoundEdges: '0',
					usePlotGradientColor: '0',
					divLineAlpha: '10',
					plotFillAlpha: '100',
					
					color: '#ffffff',
					showPlotBorder: '0',
					decimals: '2',

					showValues: '0',
					showSum: '0',
					valuePadding: '0',
					
					use3DLighting: '0', 
					canvasBaseDepth: '0', 
					numberScaleValue: '1000,1000,1000',
					numberScaleUnit: 'k,M,B',
					showshadow: '0',
					
					chartTopMargin: '6',
					chartBottomMargin: '0', 
					chartLeftMargin: '0', 
					chartRightMargin: '0',
					
					captionFontSize: '14',
					captionFontColor: '#333333',
					captionPadding: '12',
					showBorder: '0',
					plotBorderAlpha: '0',
					plotHighlightEffect: 'fadeout|color=#fff, alpha=10',
					showHoverEffect: '1',
					
		            toolTipColor: '#ffffff',
		            toolTipBorderThickness: '0',
		            toolTipBgColor: '#000000',
		            toolTipBgAlpha: '80',
		            toolTipBorderRadius: '2',
		            toolTipPadding: '5',
		            anchorradius: '6',
					anchorBorderThickness: '2',
		            
		            valueFontColor: '#000000',
		            valueFontSize: '12',
		            drawcrossline: '1',
		            exportEnabled: '1',
		            exportMode: 'client',
					exportFileName: 'cesimchart',
		            exportFormats: "PNG|SVG",
				}
			},
			angulargauge: {
				chart: {
					pivotRadius: "8",
					pivotFillMix: "#666666",

					showValue: "1",
					showshadow: "0",
					valueBelowPivot: "1",
					valueFontSize: "16",
					showGaugeBorder: "0",
					gaugefillmix: ""
				},
				dials: {
					dial: [{
						bgColor: "#444444",
						borderAlpha: "0",
						baseWidth: "8",
						topWidth: "2"
					}]
				}
			},
			msline : mstheme,
			msbar2d : mstheme,
			msstackedcolumn2d: mstheme,
			mscolumn2d: mstheme,
			stackedcolumn2d: mstheme,
			msstackedcolumn2dlinedy: mstheme,
			mscombi2d: mstheme
		}
	});

	
	var teamColors = ['#309314', '#E14444', '#5594f1', '#EE701B', '#949494', '#c07021', '#FF57A0', '#6161ab', '#B19102', '#959c11', '#c4893b', '#333333'];
					// Green,     Red,        Blue,     Orange,    Grey,      Ochre,     Pink,      Navy,      Yellow,    Olive,     Brown,     Black
	if (typeof tcs !== 'undefined')
		tcs(teamColors);	
	var teamPalette = teamColors.toString();
	

	c.addTheme({
		name: 'teamcolors',
		theme: {
			base: {
				chart: {
					paletteColors:  teamPalette
				}
			}
		}
	});
	c.addTheme({
		name: 'twovalues',
		theme: {
			base: {
				chart: {
					paletteColors: '#7CB342, #448AFF'
					// colors: 		green    blue
				}
			}
		}
	});
	c.addTheme({
		name: 'threevalues',
		theme: {
			base: {
				chart: {
					paletteColors: '#7CB342, #448AFF, #9C27B0'
					// colors: 		green    blue     purple
				}
			}
		}
	});
	c.addTheme({
		name: 'fourvalues',
		theme: {
			base: {
				chart: {
					paletteColors: '#FFAB40, #448AFF, #9C27B0, #7CB342'
					// colors: 		orange   blue     purple   green
				}
			}
		}
	});
	c.addTheme({
		name: 'products',
		theme: {
			base: {
				chart: {
					paletteColors: '#ffcd34, #7cb342, #ffee7a, #a9cd83'
					// colors: 		rubanna  andyox   rub sec  andy sec
				}
			}
		}
	});
	c.addTheme({
		name: 'products2',
		theme: {
			base: {
				chart: {
					paletteColors: '#ffcd34, #ffee7a, #7cb342, #a9cd83'
					// colors: 		rubanna  rub sec  andyox   andy sec
				}
			}
		}
	});
	c.addTheme({
		name: 'region',
		theme: {
			base: {
				chart: {
					paletteColors: '#448aff, #1d5980, #ed242d, #ffab40, #2cbeff, #6b92ac, #f37076, #ffcd34'
					// colors:      Finland  USA      France   Etc      Fi sec   USA sec  Fr sec   Etc sec
				}
			}
		}
	});
	c.addTheme({
		name: 'region2',
		theme: {
			base: {
				chart: {
					paletteColors: '#448aff, #1d5980, #ed242d, #2cbeff, #6b92ac, #f37076'
					// colors:      Finland  USA      France   Fi sec   USA sec  Fr sec 
				}
			}
		}
	});
	c.addTheme({
		name: 'preview',
		theme: {
			base: {
				chart: {
					chartTopMargin: '10',
					chartBottomMargin: '10', 
					chartLeftMargin: '25', 
					chartRightMargin: '10',
					paletteColors: '#FFAB40, #448AFF, #F5E6C2'
					// colors: 		orange   blue     ochre
				}
			}
		}
	});
	c.addTheme({
		name: 'logistics',
		theme: {
			base: {
				chart: {
					paletteColors: '#448aff, #1d5980, #2cbeff, #6b92ac, #81c784, #4db6ac, #ffab40, #b7f25a, #a9cd83'
					// colors: 		fi open  usa open fi prod  usa prod del fi   del usa  del fr   fi end   usa end
				}
			}
		}
	});
	c.addTheme({
		name: 'demandfactors',
		theme: {
			base: {
				chart: {
					paletteColors:  '#7cb342, #ffab40, #ed242d, #9c27b0'
					// colors: 		 price    advert   customer qa									
				}
			}
		}
	});
	c.addTheme({
		name: 'efficiency',
		theme: {
			base: {
				chart: {
					drawAnchors: "0",
					labelStep: "50",
		            anchorradius: '2'
				},
				"dataset": [{drawAnchors: "0"}, {drawAnchors: "1"}, {}]
			}
		}
	});
	c.addTheme({
		name: 'qualitycontrol',
		theme: {
			base: {
				chart: {
					paletteColors: '#ffcd34, #ffcd34, #7cb342, #7cb342',
					drawAnchors: "0",
					labelStep: "20"
				},
				"dataset": [{drawAnchors: "0"}, {drawAnchors: "1"}, {drawAnchors: "0"}, {drawAnchors: "1"}, {}]
			}
		}
	});
	c.addTheme({
		name: 'variablecost',
		theme: {
			base: {
				chart: {
					paletteColors: '#a9cd83, #7cb342, #2cbeff, #448aff, #ed242d, #d750a6, #9c27b0'
					// colors:      sold r   sold a   new r    new a    cost     inv r    inv a
				}
			}
		}
	});
	c.addTheme({
		name: 'percentsuffix',
		theme: {
			base: {
				chart: {
					numberSuffix: '%',
					showValues: '1'
				}
			}
		}
	});	
	c.addTheme({
		name: 'pieradius70',
		theme: {
			base: {
				chart: {
					pieRadius: '70'
				}
			}
		}
	});
	c.addTheme({
		name: 'productioncapacity',
		theme: {
			base: {
				chart: {
					paletteColors: '#448aff, #ffcd34, #7cb342'
					// colors       prod cap rubanna  andyox
				}
			}
		}
	});
	c.addTheme({
		name: 'incomecost',
		theme: {
			base: {
				chart: {
					paletteColors: '#7cb342, #448aff, #ffab40, #ffcd34, #ffee7a, #ff2751, #c60c1a'
					// colors: 		sales    income   var cost fixed co deprecia finance  taxes
				}
			}
		}
	});
	c.addTheme({
		name: 'balancesheet',
		theme: {
			base: {
				chart: {
					paletteColors: '#1D5980, #4DB6AC, #A9CD83, #7CB342, #448AFF, #FFAB40, #ED242D, #c3e18f, #b7f25a'
					// colors:      fixed as inventor receivea cash equ equity   longloan shortloa payments acc payments
				}
			}
		}
	});
	c.addTheme({
		name: 'cashflow',
		theme: {
			base: {
				chart: {
					paletteColors: '#a9cd83, #7cb342, #448aff'
					// colors:      cash fl  capital  financing
				}
			}
		}
	});
	c.addTheme({
		name: 'productionplanning',
		theme: {
			base: {
				chart: {
					paletteColors: '#448AFF, #9C27B0, #7CB342, #A9CD83, #FFAB40, #6B92AC'
					// colors:      b inv    product  deliver  add del  uns dem  en invent
				}
			}
		}
	});
	c.addTheme({
		name: 'marketingsalesprofit',
		theme: {
			base: {
				chart: {
					paletteColors: '#7cb342, #ffab40, #448aff'
					// colors:      sales    costs    profit
				}
			}
		}
	});
	c.addTheme({
		name: 'capacity',
		theme: {
			base: {
				chart: {
					paletteColors: '#1D5980, #6B92AC, #7CB342, #A9CD83, #448AFF, #2CBEFF'
					// colors:      sales    demand   build    build c  machin   machin c
				}
			}
		}
	});
	c.addTheme({
		name: 'marketreport',
		theme: {
			base: {
				chart: {
					paletteColors: '#448aff, #1d5980, #2cbeff, #6b92ac, #ffcd34, #ffab40, #b7f25a, #4db6ac, #f37076, #7cb342, #a9cd83, #0071bc, #FF8A65, #7986CB'
					// colors:		FINinv   USAInv   FinPro   USAPro   FinAdd   USAAdd   DelFin,  DelUSA   DelFra   FinEnd   USA End  add-clr  add-clr  add-clr
									
				}
			}
		}
	});
	c.addTheme({
		name: 'productsrubanna',
		theme: {
			base: {
				chart: {
					paletteColors: '#FFCD34, #9C27B0',
					//				rub      dot
					lineAlpha: '0.1'
				}
			}
		}
	});
	c.addTheme({
		name: 'productsandyox',
		theme: {
			base: {
				chart: {
					paletteColors: '#7CB342, #9C27B0',
					//				andy     dot
					lineAlpha: '0.1'
				}
			}
		}
	});
	c.addTheme({
		name: 'esgreport',
		theme: {
			base: {
				chart: {
					paletteColors: '#7CB342, #448AFF, #9C27B0',
					//				sustain  social   govern
					lineAlpha: '0.1'
				}
			}
		}
	});
	c.addTheme({
		name: 'valuecreation',
		theme: {
			base: {
				chart: {
					paletteColors: '#448AFF, #FFDE7A, #FFAB40, #ED242D, #9C27B0'
					// colors: 	    shareh   creditor personn  governm  suppliers
				}
			}
		}
	});
	c.addTheme({
		name: 'corporatebs',
		theme: {
			base: {
				chart: {
					paletteColors: '#7CB342, #448AFF, #FFAB40, #ED242D'
					// colors:      cash     equity   long l   short l
				}
			}
		}
	});


	var preview = {theme: "common, preview"};
	var teamcolors = {theme: "common, teamcolors"};
	var twovalues = {theme: "common, twovalues"};
	var threevalues = {theme: "common, threevalues"};
	var fourvalues = {theme: "common, fourvalues"};
	var region = {theme: "common, region"};
	var region2 = {theme: "common, region2"};
	var products = {theme: "common, products"};
	var products2 = {theme: "common, products2"};
	var productsrubanna = {theme: "common, productsrubanna"};
	var productsandyox = {theme: "common, productsandyox"};
	var logistics = {theme: "common, logistics"};
	var demandfactors = {theme: "common, demandfactors"};
	var efficiency = {theme: "common, efficiency"};
	var variablecost = {theme: "common, variablecost"};
	var capacity = {theme: "common, capacity"};
	var productioncapacity = {theme: "common, productioncapacity"};
	var incomecost = {theme: "common, incomecost"};
	var balancesheet = {theme: "common, balancesheet"};
	var cashflow = {theme: "common, cashflow"};
	var marketingsalesprofit = {theme: "common, marketingsalesprofit"};
	var marketreport = {theme: "common, marketreport"};
	var qualitycontrol = {theme: "common, qualitycontrol"};

	
	c.init({
		// Frontpage
		"preview-1"												: preview,
		"preview-2"												: preview,
		"preview-3"												: preview,

		// DSS, Sales 
		"MarketReport.Product1.Logistics"						: logistics,
		"MarketReport.Product2.Logistics"						: logistics,

		// DSS, Market Report
		"MarketReport.Prod1.Log"              				 	: marketreport,
		"MarketReport.Prod2.Log"              				 	: marketreport,

		// DSS, Demand Factors
		"Graphs.Sales.Market1.Product1"              			: demandfactors,
		"Graphs.Sales.Market1.Product2"              			: demandfactors,
		"Graphs.Sales.Market2.Product1"              			: demandfactors,
		"Graphs.Sales.Market2.Product2"              			: demandfactors,
		"Graphs.Sales.Market3.Product1"              			: demandfactors,
		"Graphs.Sales.Market3.Product2"              			: demandfactors,

		// DSS, Production - planning
		"chart.production.planning"         					: { theme: "common, productionplanning" },
		"chart.capacity.planning.domestic"         				: capacity,
		"chart.capacity.planning.machinery1"         			: capacity,
		"chart.capacity.planning.machinery2"         			: capacity,
		
		// DSS, Production - cost efficiency
		"cost.efficiency.chart"         						: efficiency,
		"cost.effeciency.dom.chart"         					: efficiency,
		"cost.effeciency.int.chart"         					: efficiency,

		// DSS, Production - quality control
		"quality.control.chart"         						: qualitycontrol,
		"cost.efficiency.chart"									: qualitycontrol,

		// Results, Summary
		"Graphs.Results.Summary.CumulRevenue.TimeSeries"		: teamcolors,
		"Graphs.Summary.Profitability"							: threevalues,
		"Graphs.Summary.Costs"									: variablecost,
		"Graphs.Summary.Costs.summary"							: variablecost,
		"Graphs.Results.Summary.Profits.TimeSeries"				: teamcolors,
		"Graphs.Results.Summary.CumulEarnings.TimeSeries"		: teamcolors,		
		"Graphs.Results.Summary.CumulRevenue.TimeSeries.summary": teamcolors,
		"Graphs.Results.Summary.Profits.TimeSeries.summary"		: teamcolors,
		"Graphs.Results.Summary.CumulEarnings.TimeSeries.summary": teamcolors,
		"Graphs.Results.Summary.ESG.Cumulative.Combined.TimeSeries": teamcolors,


		// Results, Market Report
		"Graphs.Market.MarketShare.Global"						: { theme: "common, teamcolors, percentsuffix, pieradius70" },
		"Graphs.Market.MarketShare.Product"						: { theme: "common, products, percentsuffix, pieradius70" },
		"Graphs.Clobal.Product.MarketValue"						: { theme: "common, products, percentsuffix, pieradius70" },
		"Graphs.Clobal.Product.MarketSize"						: { theme: "common, products, percentsuffix, pieradius70" },
		"Graphs.Market.Prod1.Mark1.overview"					: productsrubanna,
		"Graphs.Market.Prod1.Mark2.overview"					: productsrubanna,
		"Graphs.Market.Prod1.Mark3.overview"					: productsrubanna,
		"Graphs.Market.Prod2.Mark1.overview"					: productsandyox,
		"Graphs.Market.Prod2.Mark2.overview"					: productsandyox,
		"Graphs.Market.Prod2.Mark3.overview"					: productsandyox,

		// Results, Production report
		"Graph.Production.Capacity.Domestic"					: productioncapacity,
		"Graph.Production.CapacityUtil"							: region,
		"Graph.Production.Capacity.International1"				: productioncapacity,
		"Graph.Production.Personnel"							: region,
		"Graphs.Results.No.Of.Employees.Finland.TimeSeries"		: teamcolors,
		"Graphs.Results.No.Of.Employees.USA.TimeSeries"			: teamcolors,

		// Results, Logistics report
		"Graphs.Logistics.Inventories"							: products,
		"Graphs.Logistics.RubbanaDomDeliveries"					: region,
		"Graphs.Logistics.AndyOxDomDeliveries"					: region,
		"Graphs.Logistics.DirectCosts"							: products,
		"Graphs.Logistics.RubbanaInternatDeliveries"			: region,
		"Graphs.Logistics.AndyOxInternatDeliveries"				: region,
		
		// Results, Income statement
		"Graphs.IS" 											: incomecost,

		// Results, Balance sheet
		"Graphs.BS"												: balancesheet,

		// Results, Cash flow statement
		"Graphs.CFS"											: cashflow,
				
		// Results, Ratios
		"Graphs.Ratios.summary"									: teamcolors,
		"Graphs.Ratios"											: teamcolors,
		"Graphs.Results.Ratios.SharePrice.TimeSeries"			: teamcolors,
		"Graphs.Results.Ratios.SharePrice.TimeSeries.summary"	: teamcolors,

		// Results, ESG
		"Graphs.Results.Global.ESG.factors"						: { theme: "common, esgreport" },

		// Results, Value creation
		"Graph.Firm.Results.Valuecreation"						: { theme: "common, valuecreation" },

		"se.dss.finance.graph.bs.chart"							: { theme: "common, corporatebs" },

		// Slides
		"Graphs.IS_slide"										: incomecost,
		"Graphs.BS_slide"										: balancesheet,
		"Graphs.CFS_slide"										: cashflow,
		"Graphs.Slideshow.Profitability_slide"					: marketingsalesprofit,
		"Slideshow.Personnel.Shifts_slide"						: region,
		"Slideshow.Personnel.Count_slide"						: products,		
		"Graphs.Prod.Fin_slide"									: productioncapacity,
		"Graphs.Prod.Us_slide"									: productioncapacity,
		"Graphs.Summary.Costs_slide"							: variablecost,
		"Graphs.Results.Ratios.SharePrice.TimeSeries_slide"		: teamcolors,
		"Graphs.Results.Summary.Profits.TimeSeries_slide"		: teamcolors,
		"Slideshow.MnScosts_slide"								: marketingsalesprofit,
		"Graphs.Results.Summary.CumulRevenue.TimeSeries_slide"	: teamcolors,
		"Graphs.Results.Summary.GlobalMarketShare.TimeSeries_slide" : teamcolors,
		"Graphs.Market.Inventory_slide" 						: products,
		"Graphs.Others.Margin_slide"							: region2,
		"Graph.Production.Efficiency_slide"						: products2,
		"Graphs.BS.Equity_slide"								: teamcolors,
		"Graphs.Results.Summary.ESG.Cumulative.Combined.TimeSeries_slide": teamcolors,
	});
}(Chart, jQuery));