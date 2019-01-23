$(function() {
    $('#register_button').on('click', function() {
        window.location.href = "{% url 'bitbank:user_create' %}";
    });
});