$( ".projections-handle, .projections-panel-header__icon").click( function() {
    $(".projections-panel-underlay").toggleClass("projections-panel-underlay--show");

    $(".projections-handle").toggleClass("projections-handle--clicked");
    $("body").removeClass("noscroll");

    if(jQuery(window).width() < 700 ) {
        $(".sub-menu.menu-level0").slideToggle(0,'sub-menu--reveal');
        $(".page-header").slideToggle(0,'page-header');
    }
});