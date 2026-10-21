# kotlinx.serialization: keep generated serializers for wire models
-keepattributes *Annotation*, InnerClasses, Signature, RuntimeVisibleAnnotations
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class com.homelab.commandcentre.core.api.** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.homelab.commandcentre.core.api.**$$serializer { *; }
# Retrofit service interfaces are used reflectively
-keep interface com.homelab.commandcentre.core.api.AuthApi { *; }
-keep interface com.homelab.commandcentre.core.api.HomeLabApi { *; }
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
