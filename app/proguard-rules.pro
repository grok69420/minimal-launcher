# kotlinx.serialization ships its own R8 rules; keep our model serializers explicitly as well.
-keepattributes *Annotation*, InnerClasses
-keep,includedescriptorclasses class com.abhi.startuplaw.data.**$$serializer { *; }
-keepclassmembers class com.abhi.startuplaw.data.** { *** Companion; }
-keepclasseswithmembers class com.abhi.startuplaw.data.** { kotlinx.serialization.KSerializer serializer(...); }
