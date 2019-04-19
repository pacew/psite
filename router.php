<?php

if (preg_match ('|^/([-_a-zA-Z0-9]+.php)$|', 
                $_SERVER['SCRIPT_NAME'],
                $script_matches)) {
    $script_name = $script_matches[1];
    $script_fullname = sprintf ("%s/%s", $_SERVER['APP_ROOT'], $script_name);
    if (file_exists ($script_fullname)) {
        require ($script_fullname);
        /* should not return */
        echo ("route error " . $script_name);
        exit();
    } else {
        echo ("missing script " . $script_name);
        exit();
    }
}
