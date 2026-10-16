var Cesim = (function () {


    // Hamburger and overlays
    $(document).ready(function() {
        $('.hamburger, .toolbar__overlay').click(function() {
            $('.main-menu').toggleClass('toolbar--open');
            $('.toolbar__overlay').toggleClass('toolbar__overlay--show');
        });
    
        $('.main-menu__item, .hamburger, .main-menu__close, .toolbar__overlay').click(function() {
            $('body').toggleClass('noscroll');
        });
    
        $('.main-menu__container, .toolbar__overlay').click(function() {
            $('body').removeClass('noscroll');
        });
    
        $('.tools-button').click(function() {
            $('.sidebar-tools').toggleClass('sidebar-tools--open');
        });
    })
    

    // header click triggers checkbox (suppliers in ESG)
    $.fn.headerclick = function(a) {
        $("." + a + "__heading1").on("click", function(){
            $("." + a + "__checkbox1 input:checkbox").trigger("click");
        });
        $("." + a + "__heading2").on("click", function(){
            $("." + a + "__checkbox2 input:checkbox").trigger("click");
        });
        $("." + a + "__heading3").on("click", function(){
            $("." + a + "__checkbox3 input:checkbox").trigger("click");
        });
        $("." + a + "__heading4").on("click", function(){
            $("." + a + "__checkbox4 input:checkbox").trigger("click");
        });
    }

    return {
        // Panel height in ESG
        panelheights: function(divclass) {
            if($(window).width() >= 760) {
                var headheights = $(divclass + " tr:first-child").map(function() {
                    return $(this).height();
                }).get(),
                maxHeight = Math.max.apply(null, headheights);
                $(divclass + " tr:first-child").height(maxHeight);
    
                var descheights = $("[class*=js-cell-height]").map(function() {
                    return $(this).height();
                }).get(),
                maxHeight = Math.max.apply(null, descheights);
                $("[class*=js-cell-height]").height(maxHeight);
            }
        },
        
        // Panel height in ESG, bigger tables
        panelheights2: function(divclass) {
            if($(window).width() >= 760) {
                var blockheights = $(divclass).map(function() {
                    return $(this).height();
                }).get(),
                maxHeight = Math.max.apply(null, blockheights);
                $(divclass).height(maxHeight);
            }
        },       

        // Header click triggers checkbox (suppliers in ESG)
        headerclick: function(divclass) {
            $(divclass + "__heading1").on("click", function(){
                $(divclass + "__checkbox1 input:checkbox").trigger("click");
            });
            $(divclass + "__heading2").on("click", function(){
                $(divclass + "__checkbox2 input:checkbox").trigger("click");
            });
            $(divclass + "__heading3").on("click", function(){
                $(divclass + "__checkbox3 input:checkbox").trigger("click");
            });
            $(divclass + "__heading4").on("click", function(){
                $(divclass + "__checkbox4 input:checkbox").trigger("click");
            });
        },

        // Accordion (Loans pages in Loans)
        accordion: function(divclass) {
			$(document).on('click', `[class*="${divclass}__accordion-heading"]`, function (e) {
				let match = this.className.match(new RegExp(`${divclass}__accordion-heading(\\d+)`));
				if (match) {
					let index = match[1];
					$(`.${divclass}__accordion-content${index}`).toggleClass(`${divclass}__accordion-content${index}--visible`);
				}
				e.preventDefault();
			});
		},

        // Hide empty panels (GC Events and Marketing)
        hideemptypanels: function(divclass) {
            const divs = document.querySelectorAll(divclass);
            divs.forEach(div => {
                const table = div.querySelector('table');
                if (table) {
                    const tdElements = table.querySelectorAll('td');
                    if (tdElements.length === 0) {
                        div.remove();
                    }
                }
            });
        },
        
        // Select all checkboxes
        checkboxgroup: function(masterSelector, itemSelector) {
            $(masterSelector).click(function () {
                const isChecked = this.checked;
                $(itemSelector).prop('checked', isChecked);
            });
            $(itemSelector).click(function () {
                const total = $(itemSelector).length;
                const checked = $(itemSelector + ':checked').length;
                $(masterSelector).prop('checked', total === checked);
            });
        }
        
    }

}());